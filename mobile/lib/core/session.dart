import 'package:flutter/foundation.dart';

/// Holds the logged-in user's token and which company is "active" right
/// now. A ChangeNotifier so main.dart can rebuild (login screen <-> app)
/// the moment auth state changes, without any state-management package.
///
/// Phase 5 TODO: this is in-memory only — closing the app logs the user
/// out. Persisting the token (flutter_secure_storage) so login survives
/// an app restart is the next thing to add here, without changing how
/// the rest of the app reads AppSession.instance.
class AppSession extends ChangeNotifier {
  AppSession._();
  static final AppSession instance = AppSession._();

  String? _token;
  int? _companyId;
  String? _companyName;
  String? _userName;

  String? get token => _token;
  int? get companyId => _companyId;
  String? get companyName => _companyName;
  String? get userName => _userName;
  bool get isLoggedIn => _token != null;
  bool get hasActiveCompany => _companyId != null;

  void setAuth({required String token, required String userName}) {
    _token = token;
    _userName = userName;
    notifyListeners();
  }

  void setActiveCompany({required int id, required String name}) {
    _companyId = id;
    _companyName = name;
    notifyListeners();
  }

  void logout() {
    _token = null;
    _companyId = null;
    _companyName = null;
    _userName = null;
    notifyListeners();
  }
}
