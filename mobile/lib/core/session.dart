import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Holds the logged-in user's token and which company is "active" right
/// now. A ChangeNotifier so main.dart can rebuild (login screen <-> app)
/// the moment auth state changes, without any state-management package.
///
/// Phase 5: the session now SURVIVES app restarts. Token, company and user
/// name are stored in flutter_secure_storage (Android Keystore-backed), and
/// restored once at startup by [restore] before the first frame renders.
/// A stale token simply gets a 401 on the next API call, which logs out —
/// no extra validation round-trip at startup.
class AppSession extends ChangeNotifier {
  AppSession._();
  static final AppSession instance = AppSession._();

  static const _storage = FlutterSecureStorage();
  static const _kToken = 'hesabatak_token';
  static const _kCompanyId = 'hesabatak_company_id';
  static const _kCompanyName = 'hesabatak_company_name';
  static const _kUserName = 'hesabatak_user_name';
  static const _kUserEmail = 'hesabatak_user_email';

  String? _token;
  int? _companyId;
  String? _companyName;
  String? _userName;
  String? _userEmail;

  String? get token => _token;
  int? get companyId => _companyId;
  String? get companyName => _companyName;
  String? get userName => _userName;
  String? get userEmail => _userEmail;
  bool get isLoggedIn => _token != null;
  bool get hasActiveCompany => _companyId != null;

  Future<void> setAuth({required String token, required String userName, String? userEmail}) async {
    _token = token;
    _userName = userName;
    _userEmail = userEmail;
    notifyListeners();
    await _storage.write(key: _kToken, value: token);
    await _storage.write(key: _kUserName, value: userName);
    if (userEmail != null) {
      await _storage.write(key: _kUserEmail, value: userEmail);
    }
  }

  Future<void> setActiveCompany({required int id, required String name}) async {
    _companyId = id;
    _companyName = name;
    notifyListeners();
    await _storage.write(key: _kCompanyId, value: id.toString());
    await _storage.write(key: _kCompanyName, value: name);
  }

  /// Call once in main() before runApp. Restores the previous session, if
  /// any, so a returning user lands directly in their company.
  Future<void> restore() async {
    try {
      final token = await _storage.read(key: _kToken);
      if (token == null) return;
      _token = token;
      _userName = await _storage.read(key: _kUserName);
      _userEmail = await _storage.read(key: _kUserEmail);
      final companyIdStr = await _storage.read(key: _kCompanyId);
      if (companyIdStr != null) {
        _companyId = int.tryParse(companyIdStr);
        _companyName = await _storage.read(key: _kCompanyName);
      }
      notifyListeners();
    } catch (_) {
      // Corrupted or unreadable storage → treat as signed out; the login
      // screen is always the safe fallback. Never crash the app on restore.
      await logout();
    }
  }

  Future<void> logout() async {
    _token = null;
    _companyId = null;
    _companyName = null;
    _userName = null;
    _userEmail = null;
    notifyListeners();
    try {
      await _storage.deleteAll();
    } catch (_) {
      // Storage already unusable — nothing more we can do here.
    }
  }
}
