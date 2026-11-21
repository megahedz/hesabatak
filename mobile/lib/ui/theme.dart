import 'package:flutter/material.dart';

/// حساباتك design system — مستوحى من التصميم المرجعي:
/// خلفية فاتحة، بطاقات بيضاء بحواف دائرية وظلال ناعمة، أزرق/كحلي أساسي،
/// وأخضر/تركوازي كلون ثانوي — مع لمسات التدرّج العصري (بنفسجي→أزرق→سيان)
/// في الأزرار والعناوين البارزة.
class AppColors {
  AppColors._();

  /// الأزرق الأساسي (الأزرار والتحديد) — مستوحى من الكحلي المضيء في اللوجو
  static const Color primary = Color(0xFF1A5C9E);

  /// الكحلي للعناوين — نفس كحلي حرف M في اللوجو
  static const Color navy = Color(0xFF123A66);

  /// كحلي داكن جدًا (داخل الأزرار المتدرّجة) — rgb(5, 6, 45)
  static const Color ink = Color(0xFF05062D);

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

/// تدرّجات الهوية — نقطة واحدة لكل تدرّج في التطبيق.
class AppGradients {
  AppGradients._();

  /// تدرّج الأزرار العصري: بنفسجي → أزرق → سيان (Uiverse cssbuttons-io).
  static const List<Color> button = [
    Color(0xFFAF40FF),
    Color(0xFF5B42F3),
    Color(0xFF00DDEB),
  ];

  /// تدرّج أحمر للأفعال الخطرة (حذف/إزالة).
  static const List<Color> danger = [
    Color(0xFFFF7A7A),
    Color(0xFFE05252),
    Color(0xFFB3123F),
  ];

  /// تدرّج الهوية الكحلي→الأزرق→التركوازي (ترويسات وخلفيات).
  static const List<Color> brand = [
    Color(0xFF123A66),
    Color(0xFF1A5C9E),
    Color(0xFF25B7A8),
  ];

  static const LinearGradient buttonGradient = LinearGradient(
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
    colors: button,
  );

  static const LinearGradient brandGradient = LinearGradient(
    begin: Alignment.topRight,
    end: Alignment.bottomLeft,
    colors: brand,
  );

  /// لمعان بنفسجي خفيف تحت الأزرار المتدرّجة.
  static List<BoxShadow> buttonGlow = [
    BoxShadow(
      color: const Color(0xFF9741FC).withOpacity(0.20),
      blurRadius: 28,
      offset: const Offset(0, 14),
    ),
  ];
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
        scrolledUnderElevation: 0,
        backgroundColor: Colors.white,
        surfaceTintColor: Colors.transparent,
        foregroundColor: AppColors.navy,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(bottom: Radius.circular(22)),
        ),
        titleTextStyle: TextStyle(
          color: AppColors.navy,
          fontSize: 19,
          fontWeight: FontWeight.w800,
          letterSpacing: -0.2,
        ),
      ),
      cardTheme: CardThemeData(
        elevation: 0,
        color: Colors.white,
        surfaceTintColor: Colors.transparent,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
        margin: EdgeInsets.zero,
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: Colors.white,
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 15),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: const BorderSide(color: AppColors.border),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: const BorderSide(color: AppColors.border),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: const BorderSide(color: AppColors.primary, width: 1.5),
        ),
        hintStyle: const TextStyle(color: AppColors.textSecondary),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          elevation: 0,
          backgroundColor: AppColors.primary,
          foregroundColor: Colors.white,
          padding: const EdgeInsets.symmetric(horizontal: 22, vertical: 14),
          minimumSize: const Size(0, 52),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
          textStyle: const TextStyle(fontSize: 15.5, fontWeight: FontWeight.w800),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: AppColors.primary,
          minimumSize: const Size(0, 50),
          padding: const EdgeInsets.symmetric(horizontal: 22, vertical: 13),
          side: const BorderSide(color: AppColors.border, width: 1.2),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
          textStyle: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700),
        ),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          foregroundColor: AppColors.primary,
          textStyle: const TextStyle(fontSize: 14, fontWeight: FontWeight.w700),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        ),
      ),
      dialogTheme: DialogThemeData(
        backgroundColor: Colors.white,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(24)),
        titleTextStyle: const TextStyle(
          fontSize: 18,
          fontWeight: FontWeight.w800,
          color: AppColors.navy,
        ),
        contentTextStyle: const TextStyle(
          fontSize: 14,
          height: 1.5,
          color: AppColors.textSecondary,
        ),
      ),
      bottomSheetTheme: const BottomSheetThemeData(
        backgroundColor: Colors.white,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(28)),
        ),
      ),
      navigationBarTheme: NavigationBarThemeData(
        height: 68,
        backgroundColor: Colors.white,
        surfaceTintColor: Colors.transparent,
        indicatorColor: AppColors.blueTint,
        elevation: 0,
        labelTextStyle: const WidgetStatePropertyAll(
          TextStyle(fontSize: 11.5, fontWeight: FontWeight.w700, color: AppColors.navy),
        ),
      ),
      chipTheme: ChipThemeData(
        backgroundColor: AppColors.greyTint,
        selectedColor: AppColors.blueTint,
        side: BorderSide.none,
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        labelStyle: const TextStyle(fontSize: 13, fontWeight: FontWeight.w700, color: AppColors.navy),
      ),
      tabBarTheme: TabBarThemeData(
        indicatorSize: TabBarIndicatorSize.tab,
        dividerColor: Colors.transparent,
        indicator: BoxDecoration(
          color: AppColors.blueTint,
          borderRadius: BorderRadius.circular(14),
        ),
        labelColor: AppColors.primary,
        unselectedLabelColor: AppColors.textSecondary,
        labelStyle: const TextStyle(fontSize: 13.5, fontWeight: FontWeight.w800),
        unselectedLabelStyle: const TextStyle(fontSize: 13.5, fontWeight: FontWeight.w600),
      ),
      checkboxTheme: CheckboxThemeData(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
        side: const BorderSide(color: AppColors.border, width: 1.4),
      ),
      dividerTheme: const DividerThemeData(color: AppColors.border, thickness: 1),
      snackBarTheme: SnackBarThemeData(
        behavior: SnackBarBehavior.floating,
        backgroundColor: AppColors.ink,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        contentTextStyle: const TextStyle(fontSize: 13.5, color: Colors.white),
      ),
      progressIndicatorTheme: const ProgressIndicatorThemeData(
        color: AppColors.primary,
        linearTrackColor: AppColors.border,
      ),
      listTileTheme: const ListTileThemeData(
        iconColor: AppColors.navy,
        textColor: AppColors.navy,
      ),
    );
    return base;
  }
}
