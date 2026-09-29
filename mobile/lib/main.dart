import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'core/api_client.dart';
import 'core/app_config.dart';
import 'core/local_store.dart';
import 'core/session.dart';
import 'core/sync_manager.dart';
import 'features/auth/login_screen.dart';
import 'features/home/home_shell.dart';
import 'ui/theme.dart';

Future<void> main() async {
  // Must run before runApp: restoring the session is async, and the first
  // frame decides between login screen and HomeShell based on its result.
  WidgetsFlutterBinding.ensureInitialized();
  await AppSession.instance.restore();
  // تسريع الدخول: نبعت ping خفيف فور الفتح ليوقظ السيرفر النائم (Render free
  // tier) أثناء ما المستخدم يكتب بياناته — fire-and-forget بدون أي انتظار.
  if (!kIsWeb) {
    ApiClient.warmUpServer(AppConfig.apiBaseUrl);
  }
  // Phase 6: local cache + sync queue must exist before any screen can
  // render from cache or enqueue an offline write. Failures here must never
  // block the app — it just runs online-only.
  try {
    await LocalStore.instance.db;
    await SyncManager.instance.start();
  } catch (_) {}
  runApp(const HesabatakApp());
}

/// Root widget. Arabic + RTL is the base experience (spec §34), not a
/// locale variant bolted on later — English is a possible future addition,
/// not the default.
class HesabatakApp extends StatelessWidget {
  const HesabatakApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'حساباتك',
      debugShowCheckedModeBanner: false,
      locale: const Locale('ar', 'EG'),
      supportedLocales: const [Locale('ar', 'EG'), Locale('en', 'US')],
      localizationsDelegates: const [
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      theme: AppTheme.light,
      home: const Directionality(
        textDirection: TextDirection.rtl,
        child: _AuthGate(),
      ),
    );
  }
}

/// Shows the login screen until AppSession has both a token AND an active
/// company selected (a brand-new user picks/creates a company as part of
/// login itself — see LoginScreen._resolveActiveCompany). Rebuilds
/// automatically whenever AppSession changes (login, logout, or company switch).
class _AuthGate extends StatelessWidget {
  const _AuthGate();

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: AppSession.instance,
      builder: (context, _) {
        final session = AppSession.instance;
        if (session.isLoggedIn && session.hasActiveCompany) {
          return const HomeShell();
        }
        return const LoginScreen();
      },
    );
  }
}
