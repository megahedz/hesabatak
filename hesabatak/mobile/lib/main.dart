import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'core/session.dart';
import 'features/auth/login_screen.dart';
import 'features/home/home_shell.dart';

void main() {
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
      theme: ThemeData(
        useMaterial3: true,
        fontFamily: 'Cairo', // Arabic-friendly font; bundle it in Phase 2 (see README)
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF0F6E5C), // calm teal-green — reads "money/trust" without looking like a bank app
          brightness: Brightness.light,
        ),
        appBarTheme: const AppBarTheme(centerTitle: true, elevation: 0),
      ),
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
