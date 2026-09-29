import 'package:flutter/material.dart';

/// حساباتك design system — مستوحى من التصميم المرجعي:
/// خلفية فاتحة، بطاقات بيضاء بحواف دائرية وظلال ناعمة، أزرق/كحلي أساسي،
/// وأخضر/تركوازي كلون ثانوي.
class AppColors {
  AppColors._();

  /// الأزرق الأساسي (الأزرار والتحديد) — مستوحى من الكحلي المضيء في اللوجو
  static const Color primary = Color(0xFF1A5C9E);

  /// الكحلي للعناوين — نفس كحلي حرف M في اللوجو
  static const Color navy = Color(0xFF123A66);

  /// التركوازي (أيقونات ولمسات) — درجة السيان/التركوازي في اللوجو
  static const Color teal = Color(0xFF25B7A8);

  /// الأخضر (رصيد، أرباح، نجاح) — أخضر سهم النمو في اللوجو
  static const Color green = Color(0xFF35D89A);

  /// أخضر داكن للنصوص فوق الخلفيات الفاتحة (تباين أعلى من green)
  static const Color greenDark = Color(0xFF1E9E6A);

  /// الأحمر (مصروفات، أرصدة مستحقة)
  static const Color red = Color(0xFFE05252);

  /// البرتقالي (تحذيرات، أسهم صاعدة)
  static const Color amber = Color(0xFFF2A93B);

  /// البنفسجي (بطاقات أصول/مصروفات)
  static const Color purple = Color(0xFF6D5BD0);

  /// خلفية الشاشة العامة
  static const Color background = Color(0xFFF6F9FD);

  /// خلفيات البطاقات الملونة (tinted cards)
  static const Color blueTint = Color(0xFFE3F0FC);
  static const Color greenTint = Color(0xFFE2F5EB);
  static const Color redTint = Color(0xFFFDE8E8);
  static const Color amberTint = Color(0xFFFFF1DD);
  static const Color purpleTint = Color(0xFFEEEAFC);
  static const Color tealTint = Color(0xFFDFF4F4);
  static const Color greyTint = Color(0xFFEFF3F8);

  /// نصوص ثانوية
  static const Color textSecondary = Color(0xFF5A6B7E);

  /// حدود الحقول والجداول
  static const Color border = Color(0xFFE3EAF3);
}

/// ثيم التطبيق الموحد — كل الشاشات تستخدمه تلقائيًا.
class AppTheme {
  AppTheme._();

  static ThemeData get light {
    final base = ThemeData(
      useMaterial3: true,
      colorScheme: ColorScheme.fromSeed(
        seedColor: AppColors.primary,
        brightness: Brightness.light,
      ).copyWith(
        primary: AppColors.primary,
        secondary: AppColors.teal,
        surface: Colors.white,
      ),
      scaffoldBackgroundColor: AppColors.background,
      appBarTheme: const AppBarTheme(
        centerTitle: true,
        elevation: 0,
        backgroundColor: AppColors.background,
        foregroundColor: AppColors.navy,
        titleTextStyle: TextStyle(
          color: AppColors.navy,
          fontSize: 18,
          fontWeight: FontWeight.w700,
        ),
      ),
      cardTheme: CardThemeData(
        elevation: 0,
        color: Colors.white,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        margin: EdgeInsets.zero,
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: Colors.white,
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide: const BorderSide(color: AppColors.border),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide: const BorderSide(color: AppColors.border),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide: const BorderSide(color: AppColors.primary, width: 1.4),
        ),
        hintStyle: const TextStyle(color: AppColors.textSecondary),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          backgroundColor: AppColors.primary,
          foregroundColor: Colors.white,
          minimumSize: const Size.fromHeight(50),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
          textStyle: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: AppColors.primary,
          minimumSize: const Size.fromHeight(48),
          side: const BorderSide(color: AppColors.primary),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
          textStyle: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700),
        ),
      ),
      navigationBarTheme: const NavigationBarThemeData(
        backgroundColor: Colors.white,
        indicatorColor: AppColors.blueTint,
      ),
      dividerTheme: const DividerThemeData(color: AppColors.border, thickness: 1),
      snackBarTheme: SnackBarThemeData(
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      ),
    );
    return base;
  }
}
