import 'dart:convert';
import 'package:http/http.dart' as http;
import 'session.dart';

/// Thin HTTP client for the حساباتك backend. Every request automatically
/// carries the logged-in user's token (from AppSession) if one is set —
/// screens never touch headers themselves.
///
/// Phase 5 note: once offline-first (spec §42) lands, this class stays the
/// same shape but every write first goes into a local Drift "sync_queue"
/// table and this client is only called by the sync worker.
class ApiClient {
  ApiClient({required this.baseUrl});

  final String baseUrl;

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
    final res = await http.post(
      Uri.parse('$baseUrl/auth/login'),
      body: {'username': phone, 'password': password},
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
  Future<Map<String, dynamic>> getDashboard(int companyId) async {
    return _get('/companies/$companyId/dashboard');
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
    return _get('/companies/$companyId/customers/$customerId/statement');
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
    return _get('/companies/$companyId/suppliers/$supplierId/statement');
  }

  // ---------------------------------------------------------------- operations
  Future<Map<String, dynamic>> postSale({
    required int companyId,
    required double amount,
    required bool isCredit,
    required String method,
    int? customerId,
  }) {
    return _post('/companies/$companyId/operations/sale', {
      'amount': amount.toString(),
      'is_credit': isCredit.toString(),
      'method': method,
      if (customerId != null) 'customer_id': customerId.toString(),
    }, useQueryParams: true);
  }

  Future<Map<String, dynamic>> postPurchase({
    required int companyId,
    required double amount,
    required bool isCredit,
    required String method,
    int? supplierId,
    bool goesToInventory = false,
  }) {
    return _post('/companies/$companyId/operations/purchase', {
      'amount': amount.toString(),
      'is_credit': isCredit.toString(),
      'method': method,
      'goes_to_inventory': goesToInventory.toString(),
      if (supplierId != null) 'supplier_id': supplierId.toString(),
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
  }) {
    return _post('/companies/$companyId/operations/expense', {
      'amount': amount.toString(),
      'method': method,
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
  Future<Map<String, dynamic>> getTrialBalance(int companyId) => _get('/companies/$companyId/reports/trial-balance');
  Future<Map<String, dynamic>> getBalanceSheet(int companyId) => _get('/companies/$companyId/reports/balance-sheet');
  Future<Map<String, dynamic>> getProfitAndLoss(int companyId) => _get('/companies/$companyId/reports/profit-and-loss');

  // ---------------------------------------------------------------- internals
  Future<dynamic> _get(String path) async {
    final res = await http.get(Uri.parse('$baseUrl$path'), headers: _headers);
    _checkOk(res);
    return jsonDecode(res.body);
  }

  /// The backend's write endpoints take their arguments as query params
  /// (FastAPI function parameters), not a JSON body — useQueryParams=true
  /// reflects that; it's true everywhere in this client except /auth/login,
  /// which needs a real form body for OAuth2PasswordRequestForm.
  Future<Map<String, dynamic>> _post(String path, Map<String, String> params, {required bool useQueryParams}) async {
    final uri = useQueryParams
        ? Uri.parse('$baseUrl$path').replace(queryParameters: params)
        : Uri.parse('$baseUrl$path');
    final res = await http.post(uri, headers: _headers);
    _checkOk(res);
    return jsonDecode(res.body) as Map<String, dynamic>;
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

class ApiException implements Exception {
  ApiException(this.statusCode, this.body);
  final int statusCode;
  final String body;
}
