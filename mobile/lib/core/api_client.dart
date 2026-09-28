import 'dart:convert';
import 'package:http/http.dart' as http;
import 'local_store.dart';
import 'session.dart';
import 'sync_manager.dart';

/// Thin HTTP client for the حساباتك backend. Every request automatically
/// carries the logged-in user's token (from AppSession) if one is set —
/// screens never touch headers themselves.
///
/// Phase 6 offline-first (spec §42/§43): every successful GET is cached in
/// [LocalStore], and `_get` falls back to that cache on network failure.
/// `_post` funnels through [sendQueued]; the offline path enqueues instead
/// of throwing, and SyncManager replays the queue FIFO when back online.
class ApiClient {
  ApiClient({required this.baseUrl});

  final String baseUrl;

  /// Render's free tier can leave the service asleep after inactivity, so the
  /// first request after a while may take noticeably longer than usual. Give
  /// it a generous-but-bounded window instead of hanging forever.
  static const _timeout = Duration(seconds: 45);

  /// One silent retry for transient network failures (mobile networks drop
  /// DNS/signal for a second all the time). Applied to network-level errors
  /// only — never to HTTP error statuses, which are deterministic.
  static const _maxAttempts = 2;

  Map<String, String> get _headers {
    final token = AppSession.instance.token;
    return token != null ? {'Authorization': 'Bearer $token'} : {};
  }

  // ---------------------------------------------------------------- auth
  Future<Map<String, dynamic>> register({required String fullName, required String phone, required String password}) {
    return _post('/auth/register', {'full_name': fullName, 'phone': phone, 'password': password}, useQueryParams: true);
  }

  /// Login uses OAuth2's standard form-body shape (spec: JWT auth), not
  /// query params like the rest of the API, because FastAPI's
  /// OAuth2PasswordRequestForm expects application/x-www-form-urlencoded.
  Future<Map<String, dynamic>> login({required String phone, required String password}) async {
    final res = await _send(
      () => http.post(
        Uri.parse('$baseUrl/auth/login'),
        body: {'username': phone, 'password': password},
      ),
    );
    _checkOk(res);
    return jsonDecode(res.body) as Map<String, dynamic>;
  }

  // ---------------------------------------------------------------- companies
  Future<List<dynamic>> listMyCompanies() async {
    final res = await _get('/companies');
    return res as List<dynamic>;
  }

  Future<Map<String, dynamic>> createCompany({required String name, String businessType = 'عام'}) {
    return _post('/companies', {'name': name, 'business_type': businessType}, useQueryParams: true);
  }

  // ---------------------------------------------------------------- dashboard
  Future<Map<String, dynamic>> getDashboard(int companyId, {DateTime? periodStart}) async {
    final q = periodStart != null ? '?start=${periodStart.toIso8601String().substring(0, 10)}' : '';
    return (await _get('/companies/$companyId/dashboard$q', cacheKey: 'dashboard')) as Map<String, dynamic>;
  }

  // ---------------------------------------------------------------- customers
  Future<List<dynamic>> getCustomers(int companyId) async {
    final res = await _get('/companies/$companyId/customers');
    return res as List<dynamic>;
  }

  Future<Map<String, dynamic>> createCustomer({
    required int companyId,
    required String name,
    String? phone,
    double openingBalance = 0,
  }) {
    return _post('/companies/$companyId/customers', {
      'name': name,
      if (phone != null && phone.isNotEmpty) 'phone': phone,
      'opening_balance': openingBalance.toString(),
    }, useQueryParams: true);
  }

  Future<Map<String, dynamic>> getCustomerStatement(int companyId, int customerId) async {
    return (await _get('/companies/$companyId/customers/$customerId/statement')) as Map<String, dynamic>;
  }

  /// Products for the invoice item pickers (اسم، سعر البيع، سعر الشراء، المخزون).
  Future<List<dynamic>> getProducts(int companyId) async {
    final res = await _get('/companies/$companyId/products');
    return res as List<dynamic>;
  }

  /// Customer receivable balances: (customer_id → ledger balance).
  Future<Map<int, double>> getCustomerBalances(int companyId) async {
    final data = await _get('/companies/$companyId/customers/balances');
    return (data as Map<String, dynamic>)
        .map((k, v) => MapEntry(int.parse(k), (v as num).toDouble()));
  }

  /// Supplier payable balances: (supplier_id → ledger balance).
  Future<Map<int, double>> getSupplierBalances(int companyId) async {
    final data = await _get('/companies/$companyId/suppliers/balances');
    return (data as Map<String, dynamic>)
        .map((k, v) => MapEntry(int.parse(k), (v as num).toDouble()));
  }

  /// General-ledger rows for one account (الخزنة والبنك / الأصول الثابتة screens).
  Future<Map<String, dynamic>> getGeneralLedger(int companyId, String accountCode) async {
    return (await _get('/companies/$companyId/reports/general-ledger?account_code=$accountCode'))
        as Map<String, dynamic>;
  }

  /// Company settings (VAT / inventory / fiscal year / name).
  Future<Map<String, dynamic>> getSettings(int companyId) async {
    return (await _get('/companies/$companyId/settings', cacheKey: 'settings')) as Map<String, dynamic>;
  }

  /// Partial settings update — only non-null fields are sent.
  Future<Map<String, dynamic>> updateSettings(
    int companyId, {
    String? name,
    String? businessType,
    bool? vatEnabled,
    double? vatRate,
    bool? inventoryEnabled,
    int? fiscalYearStartMonth,
  }) {
    return _post('/companies/$companyId/settings', {
      if (name != null && name.trim().isNotEmpty) 'name': name,
      if (businessType != null) 'business_type': businessType,
      if (vatEnabled != null) 'vat_enabled': vatEnabled.toString(),
      if (vatRate != null) 'vat_rate': vatRate.toString(),
      if (inventoryEnabled != null) 'inventory_enabled': inventoryEnabled.toString(),
      if (fiscalYearStartMonth != null) 'fiscal_year_start_month': fiscalYearStartMonth.toString(),
    }, useQueryParams: true);
  }

  /// Creates a product. With opening stock > 0, the server requires a
  /// purchase price and posts the stock value as owner capital.
  Future<Map<String, dynamic>> createProduct(
    int companyId, {
    required String name,
    String? sku,
    String unit = 'قطعة',
    double purchasePrice = 0,
    double sellingPrice = 0,
    double openingStockQty = 0,
    double minimumStock = 0,
  }) {
    return _post('/companies/$companyId/products', {
      'name': name,
      if (sku != null && sku.trim().isNotEmpty) 'sku': sku,
      'unit': unit,
      'purchase_price': purchasePrice.toString(),
      'selling_price': sellingPrice.toString(),
      'opening_stock_qty': openingStockQty.toString(),
      'minimum_stock': minimumStock.toString(),
    }, useQueryParams: true);
  }

  // ---------------------------------------------------------------- suppliers
  Future<List<dynamic>> getSuppliers(int companyId) async {
    final res = await _get('/companies/$companyId/suppliers');
    return res as List<dynamic>;
  }

  Future<Map<String, dynamic>> createSupplier({
    required int companyId,
    required String name,
    String? phone,
    double openingBalance = 0,
  }) {
    return _post('/companies/$companyId/suppliers', {
      'name': name,
      if (phone != null && phone.isNotEmpty) 'phone': phone,
      'opening_balance': openingBalance.toString(),
    }, useQueryParams: true);
  }

  Future<Map<String, dynamic>> getSupplierStatement(int companyId, int supplierId) async {
    return (await _get('/companies/$companyId/suppliers/$supplierId/statement')) as Map<String, dynamic>;
  }

  // ---------------------------------------------------------------- operations
  /// [items] rows: {product_id, quantity, unit_price} — serialized as a JSON
  /// string param so the offline sync queue (Map<String,String>) can carry it.
  Future<Map<String, dynamic>> postSale({
    required int companyId,
    required double amount,
    required bool isCredit,
    required String method,
    int? customerId,
    double vatAmount = 0,
    List<Map<String, dynamic>>? items,
  }) {
    return _post('/companies/$companyId/operations/sale', {
      'amount': amount.toString(),
      'is_credit': isCredit.toString(),
      'method': method,
      'vat_amount': vatAmount.toString(),
      if (customerId != null) 'customer_id': customerId.toString(),
      if (items != null && items.isNotEmpty) 'items_json': jsonEncode(items),
    }, useQueryParams: true);
  }

  /// [items] rows: {product_id, quantity, unit_price} — same JSON-string
  /// serialization as [postSale] (the offline queue is Map<String,String>).
  /// When [items] is non-empty the server forces the purchase into inventory
  /// and requires amount == sum of line totals.
  Future<Map<String, dynamic>> postPurchase({
    required int companyId,
    required double amount,
    required bool isCredit,
    required String method,
    int? supplierId,
    bool goesToInventory = false,
    double vatAmount = 0,
    List<Map<String, dynamic>>? items,
  }) {
    return _post('/companies/$companyId/operations/purchase', {
      'amount': amount.toString(),
      'is_credit': isCredit.toString(),
      'method': method,
      'goes_to_inventory': goesToInventory.toString(),
      'vat_amount': vatAmount.toString(),
      if (supplierId != null) 'supplier_id': supplierId.toString(),
      if (items != null && items.isNotEmpty) 'items_json': jsonEncode(items),
    }, useQueryParams: true);
  }

  Future<Map<String, dynamic>> postCustomerPayment({
    required int companyId,
    required double amount,
    required int customerId,
    required String method,
  }) {
    return _post('/companies/$companyId/operations/customer-payment', {
      'amount': amount.toString(),
      'customer_id': customerId.toString(),
      'method': method,
    }, useQueryParams: true);
  }

  Future<Map<String, dynamic>> postSupplierPayment({
    required int companyId,
    required double amount,
    required int supplierId,
    required String method,
  }) {
    return _post('/companies/$companyId/operations/supplier-payment', {
      'amount': amount.toString(),
      'supplier_id': supplierId.toString(),
      'method': method,
    }, useQueryParams: true);
  }

  Future<Map<String, dynamic>> postExpense({
    required int companyId,
    required double amount,
    required String method,
    String? expenseAccountCode,
  }) {
    return _post('/companies/$companyId/operations/expense', {
      'amount': amount.toString(),
      'method': method,
      if (expenseAccountCode != null) 'expense_account_code': expenseAccountCode,
    }, useQueryParams: true);
  }

  Future<Map<String, dynamic>> postCapital({
    required int companyId,
    required double amount,
    required String method,
  }) {
    return _post('/companies/$companyId/operations/capital', {
      'amount': amount.toString(),
      'method': method,
    }, useQueryParams: true);
  }

  Future<Map<String, dynamic>> postOwnerWithdrawal({
    required int companyId,
    required double amount,
    required String method,
  }) {
    return _post('/companies/$companyId/operations/owner-withdrawal', {
      'amount': amount.toString(),
      'method': method,
    }, useQueryParams: true);
  }

  Future<Map<String, dynamic>> postTransfer({
    required int companyId,
    required double amount,
    required String fromCode,
    required String toCode,
  }) {
    return _post('/companies/$companyId/operations/transfer', {
      'amount': amount.toString(),
      'from_code': fromCode,
      'to_code': toCode,
    }, useQueryParams: true);
  }

  // ---------------------------------------------------------------- reports
  Future<Map<String, dynamic>> getTrialBalance(int companyId) async =>
      (await _get('/companies/$companyId/reports/trial-balance', cacheKey: 'trial_balance')) as Map<String, dynamic>;
  Future<Map<String, dynamic>> getBalanceSheet(int companyId) async =>
      (await _get('/companies/$companyId/reports/balance-sheet', cacheKey: 'balance_sheet')) as Map<String, dynamic>;
  Future<Map<String, dynamic>> getProfitAndLoss(int companyId) async =>
      (await _get('/companies/$companyId/reports/profit-and-loss', cacheKey: 'profit_and_loss')) as Map<String, dynamic>;

  // ------------------------------------------------- detailed reports (Phase 6)
  Future<Map<String, dynamic>> getSalesReport(int companyId) async =>
      (await _get('/companies/$companyId/reports/sales', cacheKey: 'sales_report')) as Map<String, dynamic>;

  Future<Map<String, dynamic>> getPurchasesReport(int companyId) async =>
      (await _get('/companies/$companyId/reports/purchases', cacheKey: 'purchases_report')) as Map<String, dynamic>;

  Future<Map<String, dynamic>> getInventoryReport(int companyId) async =>
      (await _get('/companies/$companyId/reports/inventory', cacheKey: 'inventory_report')) as Map<String, dynamic>;

  Future<Map<String, dynamic>> getExpensesReport(int companyId) async =>
      (await _get('/companies/$companyId/reports/expenses', cacheKey: 'expenses_report')) as Map<String, dynamic>;

  // ------------------------------------------------- backup / restore (Phase 6)
  /// Downloads the full company backup JSON. Returns the raw bytes plus a
  /// friendly Arabic file name (from the server's RFC 5987 header when
  /// present).
  Future<BackupFile> downloadBackup() async {
    final res = await _send(() => http.get(
          Uri.parse('$baseUrl/companies/${AppSession.instance.companyId}/backup'),
          headers: _headers,
        ));
    _checkOk(res);
    String name = 'hesabatak-backup.json';
    final disposition = res.headers['content-disposition'];
    if (disposition != null) {
      final star = RegExp(r"filename\*=UTF-8''([^;]+)").firstMatch(disposition);
      if (star != null) {
        name = Uri.decodeComponent(star.group(1)!);
      }
    }
    return BackupFile(bytes: res.bodyBytes, fileName: name);
  }

  /// Downloads a PDF/Excel export of a report (بند 39/40).
  /// [fmt] is 'pdf' or 'excel'.
  Future<BackupFile> downloadExport({required String reportKey, required String fmt}) async {
    final cid = AppSession.instance.companyId;
    final res = await _send(() => http.get(
          Uri.parse('$baseUrl/companies/$cid/export/$reportKey')
              .replace(queryParameters: {'fmt': fmt}),
          headers: _headers,
        ));
    _checkOk(res);
    String name = 'hesabatak-$reportKey.${fmt == 'excel' ? 'xlsx' : 'pdf'}';
    final disposition = res.headers['content-disposition'];
    if (disposition != null) {
      final star = RegExp(r"filename\*=UTF-8''([^;]+)").firstMatch(disposition);
      if (star != null) {
        name = Uri.decodeComponent(star.group(1)!);
      }
    }
    return BackupFile(bytes: res.bodyBytes, fileName: name);
  }

  /// Restores a backup file (replace mode). [bytes] is the raw JSON file.
  Future<Map<String, dynamic>> restoreBackup(List<int> bytes) async {
    final res = await _send(() => http.post(
          Uri.parse('$baseUrl/companies/${AppSession.instance.companyId}/restore'),
          headers: {..._headers, 'Content-Type': 'application/json'},
          body: bytes,
        ));
    if (res.statusCode == 401) AppSession.instance.logout();
    if (res.statusCode >= 400) throw ApiException(res.statusCode, res.body);
    return jsonDecode(res.body) as Map<String, dynamic>;
  }

  // ---------------------------------------------------------------- internals
  Future<dynamic> _get(String path, {String? cacheKey}) async {
    try {
      final res = await _send(() => http.get(Uri.parse('$baseUrl$path'), headers: _headers));
      _checkOk(res);
      final decoded = jsonDecode(res.body);
      if (cacheKey != null && decoded is Map<String, dynamic>) {
        // Cache best-effort; never let a storage failure break the screen.
        try {
          await LocalStore.instance.saveCache(cacheKey, decoded);
        } catch (_) {}
      }
      return decoded;
    } on ApiNetworkException {
      if (cacheKey != null) {
        final cached = await _readCacheOrThrow(cacheKey);
        if (cached != null) return cached;
      }
      rethrow;
    }
  }

  Future<Map<String, dynamic>?> _readCacheOrThrow(String cacheKey) async {
    try {
      return await LocalStore.instance.readCache(cacheKey);
    } catch (_) {
      return null;
    }
  }

  /// The backend's write endpoints take their arguments as query params
  /// (FastAPI function parameters), not a JSON body — useQueryParams=true
  /// reflects that; it's true everywhere in this client except /auth/login,
  /// which needs a real form body for OAuth2PasswordRequestForm.
  ///
  /// Phase 6: every write funnels through [sendQueued]; when the device is
  /// offline the write is stored in the sync queue (FIFO, replayed by
  /// SyncManager) and a synthetic response is returned so screens can treat
  /// it as accepted — the offline banner shows the pending count.
  Future<Map<String, dynamic>> _post(String path, Map<String, String> params, {required bool useQueryParams}) async {
    try {
      return await sendQueued(path, params);
    } on ApiNetworkException {
      // Auth and company-creation only make sense with the server reachable
      // — queueing a register call would replay garbage later.
      if (path.startsWith('/auth') || path == '/companies') rethrow;
      await SyncManager.instance.enqueueOfflineWrite(path, params);
      return const {'status': 'queued', 'offline': true};
    }
  }

  /// Sends one write immediately (used by the sync worker to replay the
  /// queue). Throws [ApiNetworkException] when offline — callers that want
  /// offline-tolerant behavior catch it and enqueue.
  Future<Map<String, dynamic>> sendQueued(String path, Map<String, String> params) async {
    final res = await _send(
      () => http.post(Uri.parse('$baseUrl$path').replace(queryParameters: params), headers: _headers),
    );
    _checkOk(res);
    return jsonDecode(res.body) as Map<String, dynamic>;
  }

  /// Wraps every HTTP call with a timeout and one retry on network-level
  /// failures. Rethrows as [ApiNetworkException] so screens can show a single
  /// friendly "no connection" message instead of a stack of socket details.
  Future<http.Response> _send(Future<http.Response> Function() request) async {
    Object? lastError;
    for (var attempt = 1; attempt <= _maxAttempts; attempt++) {
      try {
        return await request().timeout(_timeout);
      } catch (e) {
        // Only network-level failures reach here (HTTP statuses are checked
        // in _checkOk, after _send returns) — exactly what we want to retry.
        lastError = e;
      }
    }
    throw ApiNetworkException(lastError);
  }

  void _checkOk(http.Response res) {
    if (res.statusCode == 401) {
      // Token missing/expired — drop the session so the UI falls back to
      // the login screen instead of showing a confusing generic error.
      AppSession.instance.logout();
    }
    if (res.statusCode >= 400) {
      // Never surface raw HTTP/technical errors to the user (spec §49) —
      // this exception is caught higher up and mapped to a friendly Arabic message.
      throw ApiException(res.statusCode, res.body);
    }
  }
}

/// A network-level failure (DNS, timeout, socket…) after retries. Screens
/// catch this and show one friendly message — never the raw exception.
class ApiNetworkException implements Exception {
  ApiNetworkException(this.cause);
  final Object? cause;
}

class ApiException implements Exception {
  ApiException(this.statusCode, this.body);
  final int statusCode;
  final String body;
}

/// A downloaded backup: raw JSON bytes + a friendly (Arabic) file name.
class BackupFile {
  BackupFile({required this.bytes, required this.fileName});
  final List<int> bytes;
  final String fileName;
}
