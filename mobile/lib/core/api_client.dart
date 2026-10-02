import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:http_parser/http_parser.dart';
import 'local_store.dart';
import 'session.dart';
import 'sync_manager.dart';

/// Thin HTTP client for the حساباتك backend. Every request automatically
/// carries the logged-in user's token (from AppSession) if one is set —
/// screens never touch headers themselves.
///
/// ARCHITECTURE (mandatory): the cloud database on the server is the ONLY
/// source of truth. Reads may use the tiny last-known-payload display cache
/// (temporary UI data, per the architecture requirement), but WRITES are
/// strictly online-only: they go straight to the server or fail with a
/// clear message — nothing accounting-related is ever stored on the device
/// as a primary copy, and no local sync queue exists anymore.
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
  Future<Map<String, dynamic>> register({
    required String fullName,
    required String phone,
    required String email,
    required String password,
  }) {
    return _post('/auth/register', {
      'full_name': fullName,
      'phone': phone,
      'email': email,
      'password': password,
    }, useQueryParams: true);
  }

  /// Login uses OAuth2's standard form-body shape (spec: JWT auth), not
  /// query params like the rest of the API, because FastAPI's
  /// OAuth2PasswordRequestForm expects application/x-www-form-urlencoded.
  ///
  /// تسجيل الدخول/التسجيل يحتاج مهلة أطول من باقي الطلبات: على الخطة المجانية
  /// من Render قد يستيقظ السيرفر أثناء الطلب نفسه (حتى ~45 ثانية)، فنفصل
  /// مهلة حرة لا تُقطع الإعادة الصامتة عندها.
  Future<Map<String, dynamic>> login({required String phone, required String password}) async {
    final res = await _send(
      () => http.post(
        Uri.parse('$baseUrl/auth/login'),
        body: {'username': phone, 'password': password},
      ).timeout(const Duration(seconds: 90)),
    );
    _checkOk(res);
    return jsonDecode(res.body) as Map<String, dynamic>;
  }

  /// Register: same long-timeout treatment as [login] — the server may be
  /// waking up from Render free tier's cold start during the request itself.
  Future<Map<String, dynamic>> registerLong({
    required String fullName,
    required String phone,
    required String email,
    required String password,
  }) async {
    final res = await _send(
      () => http.post(
        Uri.parse('$baseUrl/auth/register').replace(queryParameters: {
          'full_name': fullName,
          'phone': phone,
          'email': email,
          'password': password,
        }),
        headers: _headers,
      ).timeout(const Duration(seconds: 90)),
    );
    _checkOk(res);
    return jsonDecode(res.body) as Map<String, dynamic>;
  }

  /// Fire-and-forget wake-up ping: يُطلق فور فتح التطبيق ليوقظ السيرفر النائم
  /// أثناء ما المستخدم يكتب بياناته — أول طلب فعلي يجده مستيقظًا.
  static void warmUpServer(String baseUrl) {
    http.get(Uri.parse('$baseUrl/health')).timeout(const Duration(seconds: 75)).catchError((_) {});
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
    String? taxCardNo,
    bool? withholdingEnabled,
  }) {
    return _post('/companies/$companyId/settings', {
      if (name != null && name.trim().isNotEmpty) 'name': name,
      if (businessType != null) 'business_type': businessType,
      if (vatEnabled != null) 'vat_enabled': vatEnabled.toString(),
      if (vatRate != null) 'vat_rate': vatRate.toString(),
      if (inventoryEnabled != null) 'inventory_enabled': inventoryEnabled.toString(),
      if (fiscalYearStartMonth != null) 'fiscal_year_start_month': fiscalYearStartMonth.toString(),
      if (taxCardNo != null) 'tax_card_no': taxCardNo,
      if (withholdingEnabled != null) 'withholding_enabled': withholdingEnabled.toString(),
    }, useQueryParams: true);
  }

  /// Creates a product. With opening stock > 0, the server requires a
  /// purchase price and posts the stock value as owner capital.
  Future<Map<String, dynamic>> createProduct(
    int companyId, {
    required String name,
    String? sku,
    String unit = 'قطعة',
    String? description,
    double purchasePrice = 0,
    double sellingPrice = 0,
    double openingStockQty = 0,
    double minimumStock = 0,
  }) {
    return _post('/companies/$companyId/products', {
      'name': name,
      if (sku != null && sku.trim().isNotEmpty) 'sku': sku,
      'unit': unit,
      if (description != null && description.trim().isNotEmpty)
        'description': description.trim(),
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
    String? withholdingKind,
    double? withholdingRate,
  }) {
    return _post('/companies/$companyId/operations/sale', {
      'amount': amount.toString(),
      'is_credit': isCredit.toString(),
      'method': method,
      'vat_amount': vatAmount.toString(),
      if (customerId != null) 'customer_id': customerId.toString(),
      if (items != null && items.isNotEmpty) 'items_json': jsonEncode(items),
      if (withholdingKind != null && withholdingKind.isNotEmpty)
        'withholding_kind': withholdingKind,
      if (withholdingRate != null) 'withholding_rate': withholdingRate.toString(),
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
    String? withholdingKind,
    double? withholdingRate,
  }) {
    return _post('/companies/$companyId/operations/purchase', {
      'amount': amount.toString(),
      'is_credit': isCredit.toString(),
      'method': method,
      'goes_to_inventory': goesToInventory.toString(),
      'vat_amount': vatAmount.toString(),
      if (supplierId != null) 'supplier_id': supplierId.toString(),
      if (items != null && items.isNotEmpty) 'items_json': jsonEncode(items),
      if (withholdingKind != null && withholdingKind.isNotEmpty)
        'withholding_kind': withholdingKind,
      if (withholdingRate != null) 'withholding_rate': withholdingRate.toString(),
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
    String? notes,
    /// «مصروف مخصص»: اسم حر يكتبه المستخدم — السيرفر ينشئ حسابًا دائمًا به
    /// (أو يعيد استخدام الموجود) ويُرحّل المصروف عليه.
    String? customLabel,
  }) {
    return _post('/companies/$companyId/operations/expense', {
      'amount': amount.toString(),
      'method': method,
      if (expenseAccountCode != null) 'expense_account_code': expenseAccountCode,
      if (notes != null && notes.trim().isNotEmpty) 'notes': notes.trim(),
      if (customLabel != null && customLabel.trim().isNotEmpty) 'custom_label': customLabel.trim(),
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

  // ---------------------------------------------------------------- team & notifications (Phase 7)
  /// دور المستخدم الحالي في الشركة وصلاحياته (لتخصيص الواجهة).
  Future<Map<String, dynamic>> getMyMembership(int companyId) async {
    return (await _get('/companies/$companyId/team/me', cacheKey: 'membership')) as Map<String, dynamic>;
  }

  /// أعضاء الشركة وأدوارهم.
  Future<List<dynamic>> getTeam(int companyId) async {
    final res = await _get('/companies/$companyId/team');
    return res as List<dynamic>;
  }

  /// إضافة عضو (مستخدم مسجّل برقم هاتفه) بدور محدد. المالك فقط.
  Future<Map<String, dynamic>> addTeamMember(int companyId, {required String phone, required String role}) {
    return _post('/companies/$companyId/team/add', {
      'phone': phone,
      'role': role,
    }, useQueryParams: true);
  }

  /// تغيير دور عضو. المالك فقط.
  Future<Map<String, dynamic>> changeMemberRole(int companyId, {required int userId, required String role}) {
    return _post('/companies/$companyId/team/role', {
      'user_id': userId.toString(),
      'role': role,
    }, useQueryParams: true);
  }

  /// إزالة عضو من الشركة. المالك فقط.
  Future<Map<String, dynamic>> removeTeamMember(int companyId, {required int userId}) {
    return _post('/companies/$companyId/team/remove', {
      'user_id': userId.toString(),
    }, useQueryParams: true);
  }

  /// تنبيهات عملية: أصناف نافدة/منخفضة، عملاء مستحق لنا، موردون مستحق لهم.
  Future<Map<String, dynamic>> getNotifications(int companyId) async {
    return (await _get('/companies/$companyId/notifications', cacheKey: 'notifications'))
        as Map<String, dynamic>;
  }

  // ---------------------------------------------------------------- reports
  Future<Map<String, dynamic>> getTrialBalance(int companyId) async =>
      (await _get('/companies/$companyId/reports/trial-balance', cacheKey: 'trial_balance')) as Map<String, dynamic>;
  Future<Map<String, dynamic>> getBalanceSheet(int companyId) async =>
      (await _get('/companies/$companyId/reports/balance-sheet', cacheKey: 'balance_sheet')) as Map<String, dynamic>;
  Future<Map<String, dynamic>> getProfitAndLoss(int companyId) async =>
      (await _get('/companies/$companyId/reports/profit-and-loss', cacheKey: 'profit_and_loss')) as Map<String, dynamic>;

  // ------------------------------------------------- detailed reports (Phase 6)
  /// [period]: today | month | year (فترات سريعة). [byItem]: تجميع على أساس
  /// الصنف بالعدد والكمية والقيمة. كلها query params — الكاش يبقى بلا مفتاح
  /// ثابت حتى لا تختلط الفترات.
  Future<Map<String, dynamic>> getSalesReport(int companyId,
      {String? period, bool byItem = false}) async {
    final q = _reportQuery(period, byItem);
    return (await _get('/companies/$companyId/reports/sales$q',
        cacheKey: q.isEmpty ? 'sales_report' : null)) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getPurchasesReport(int companyId,
      {String? period, bool byItem = false}) async {
    final q = _reportQuery(period, byItem);
    return (await _get('/companies/$companyId/reports/purchases$q',
        cacheKey: q.isEmpty ? 'purchases_report' : null)) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getInventoryReport(int companyId) async =>
      (await _get('/companies/$companyId/reports/inventory', cacheKey: 'inventory_report')) as Map<String, dynamic>;

  Future<Map<String, dynamic>> getExpensesReport(int companyId, {String? period}) async {
    final q = _reportQuery(period, false);
    return (await _get('/companies/$companyId/reports/expenses$q',
        cacheKey: q.isEmpty ? 'expenses_report' : null)) as Map<String, dynamic>;
  }

  /// Query string مشترك لفترات التقارير السريعة والتجميع بالصنف.
  String _reportQuery(String? period, bool byItem) {
    final parts = <String>[
      if (period != null && period.isNotEmpty) 'period=$period',
      if (byItem) 'by_item=true',
    ];
    return parts.isEmpty ? '' : '?${parts.join('&')}';
  }

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

  /// إشعار/شهادة خصم وفق قانون 91 لسنة 2005 (PDF).
  /// [docType] = sale (إشعار من العميل) | purchase (شهادة للمورد).
  Future<BackupFile> downloadWithholdingNotice(int invoiceId,
      {required String docType}) async {
    final cid = AppSession.instance.companyId;
    final res = await _send(() => http.get(
          Uri.parse('$baseUrl/companies/$cid/withholding-notice/$docType/$invoiceId'),
          headers: _headers,
        ));
    _checkOk(res);
    String name = 'hesabatak-$docType-withholding-$invoiceId.pdf';
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

  // ---------------------------------------------------------------- attachments (المرفقات)
  /// رفع مرفق (صورة/PDF) على عميل/مورد/فاتورة بيع/فاتورة شراء/دفعة.
  /// [ownerKind] أحد: customer, supplier, sale, purchase, payment.
  Future<Map<String, dynamic>> uploadAttachment({
    required String ownerKind,
    required int ownerId,
    required List<int> bytes,
    required String fileName,
    required String contentType,
  }) async {
    final cid = AppSession.instance.companyId;
    final uri = Uri.parse('$baseUrl/companies/$cid/attachments/$ownerKind/$ownerId');
    final req = http.MultipartRequest('POST', uri)
      ..headers.addAll(_headers)
      ..files.add(http.MultipartFile.fromBytes('file', bytes,
          filename: fileName, contentType: MediaType.parse(contentType)));
    final streamed = await req.send().timeout(const Duration(seconds: 60));
    final res = await http.Response.fromStream(streamed);
    _checkOk(res);
    return jsonDecode(res.body) as Map<String, dynamic>;
  }

  /// قائمة مرفقات مستند معين (بدون محتوى الملف).
  Future<List<dynamic>> listAttachments(String ownerKind, int ownerId) async {
    final cid = AppSession.instance.companyId;
    final res = await _get('/companies/$cid/attachments/$ownerKind/$ownerId');
    return res as List<dynamic>;
  }

  /// تنزيل محتوى مرفق واحد (الملف الأصلي).
  Future<BackupFile> downloadAttachment(String ownerKind, int ownerId, int attachmentId) async {
    final cid = AppSession.instance.companyId;
    final res = await _send(() => http.get(
          Uri.parse('$baseUrl/companies/$cid/attachments/$ownerKind/$ownerId/$attachmentId'),
          headers: _headers,
        ));
    _checkOk(res);
    String name = 'attachment-$attachmentId';
    final disposition = res.headers['content-disposition'];
    if (disposition != null) {
      final star = RegExp(r"filename\*=UTF-8''([^;]+)").firstMatch(disposition);
      if (star != null) {
        name = Uri.decodeComponent(star.group(1)!);
      }
    }
    return BackupFile(bytes: res.bodyBytes, fileName: name);
  }

  /// حذف مرفق.
  Future<void> deleteAttachment(String ownerKind, int ownerId, int attachmentId) async {
    final cid = AppSession.instance.companyId;
    final res = await _send(() => http.delete(
          Uri.parse('$baseUrl/companies/$cid/attachments/$ownerKind/$ownerId/$attachmentId'),
          headers: _headers,
        ));
    _checkOk(res);
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
  /// ARCHITECTURE: writes are ONLINE-ONLY (the server's cloud database is the
  /// single source of truth; no offline mode at this stage). A network failure
  /// surfaces immediately so the user can retry — we never store accounting
  /// writes on the device. The only local write is draining a legacy queue
  /// left by older app versions, so data saved before this update is not lost.
  Future<Map<String, dynamic>> _post(String path, Map<String, String> params, {required bool useQueryParams}) async {
    return sendQueued(path, params);
  }

  /// Sends one write immediately. Also used by the startup legacy-queue
  /// drain below: older versions could leave unsent operations on the device,
  /// and those are uploaded once so no previously recorded operation is lost.
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
