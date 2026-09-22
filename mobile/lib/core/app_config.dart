import 'session.dart';

/// Central place for environment config.
///
/// 10.0.2.2 is the special alias the Android emulator uses to reach
/// "localhost" on the host machine it's running on. On a real device,
/// change this to your computer's LAN IP (e.g. http://192.168.1.20:8000)
/// with both devices on the same Wi-Fi.
class AppConfig {
  static const String apiBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://10.0.2.2:8000',
  );

  /// The company every screen operates on. Delegates to AppSession, which
  /// is set once after login — no screen needs to change now that auth
  /// picks the company at runtime instead of this being a hardcoded constant.
  static int get companyId {
    final id = AppSession.instance.companyId;
    assert(id != null, 'AppConfig.companyId read before a company was selected');
    return id ?? -1;
  }
}
