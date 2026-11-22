import 'package:flutter/material.dart';

/// حساباتك design system — v2 «دفتر هادئ».
///
/// الاتجاه: محاسبة هادئة وواضحة. مساحات بيضاء واسعة، أخضر زمردي غامق كلون
/// أساسي (أرقام مالية مقروءة على الأبيض)، كحلي داكن للنصوص، وأيقونات خطية
/// موحّدة داخل بلاطات ناعمة. لا تدرّجات نيون ولا ظلال ثقيلة: التمييز يأتي من
/// المساحة والوزن الطباعي، لا من الألوان الصاخبة.
class AppColors {
  AppColors._();

  /// الأخضر الزمردي الأساسي — الأزرار والتحديد والعناصر النشطة.
  static const Color primary = Color(0xFF0E7C6B);

  /// كحلي العناوين والنصوص الأساسية.
  static const Color navy = Color(0xFF0A2540);

  /// الكحلي الأغمق (خلفيات داكنة، SnackBar).
  static const Color ink = Color(0xFF071A2B);

  /// التركوازي (لمسات ثانوية).
  static const Color teal = Color(0xFF12A594);

  /// الأخضر الفاتح (مؤشرات إيجابية على خلفية داكنة).
  static const Color green = Color(0xFF12B76A);

  /// الأخضر الغامق — للنصوص فوق الخلفيات الفاتحة (تباين أعلى).
  static const Color greenDark = Color(0xFF067647);

  /// الأحمر (مصروفات، أرصدة مستحقة، أفعال خطرة).
  static const Color red = Color(0xFFD92D20);

  /// البرتقالي (تحذيرات).
  static const Color amber = Color(0xFFC77700);

  /// البنفسجي (أصول/تصنيفات ثانوية).
  static const Color purple = Color(0xFF6941C6);

  /// خلفية الشاشات.
  static const Color background = Color(0xFFF4F7F9);

  /// سطح البطاقات (أبيض نقي ليطفو على الخلفية الرمادية).
  static const Color surface = Colors.white;

  /// تدرّجات باهتة للأيقونات والشرائح.
  static const Color blueTint = Color(0xFFE8F1FA);
  static const Color greenTint = Color(0xFFE4F7EE);
  static const Color redTint = Color(0xFFFDECEA);
  static const Color amberTint = Color(0xFFFDF2E2);
  static const Color purpleTint = Color(0xFFEFEBFB);
  static const Color tealTint = Color(0xFFE2F6F3);
  static const Color greyTint = Color(0xFFEFF3F7);

  /// نصوص ثانوية.
  static const Color textSecondary = Color(0xFF55677A);

  /// حدود الحقول والجداول.
  static const Color border = Color(0xFFE3E9F0);

  /// حدّ أثقل قليلًا للفواصل داخل الجداول.
  static const Color borderStrong = Color(0xFFD3DCE6);
}

/// تدرّجات الهوية — مصدر واحد لكل تدرّج في التطبيق.
class AppGradients {
  AppGradients._();

  /// زر أساسي: زمردي غامق → زمردي متوسط (الأبيض عليه مقروء دائمًا).
  static const List<Color> button = [
    Color(0xFF0B5F53),
    Color(0xFF0E8A76),
  ];

  /// أحمر للأفعال الخطرة (حذف/إزالة).
  static const List<Color> danger = [
    Color(0xFFD92D20),
    Color(0xFFB42318),
  ];

  /// الهوية: كحلي → تركوازي (لوحة الدرج، البطاقة الرئيسية).
  static const List<Color> brand = [
    Color(0xFF0A2540),
    Color(0xFF0D4E5A),
    Color(0xFF0E7C6B),
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

  /// ظل خفيف تحت الزر الأساسي (زمردي، شفافية منخفضة).
  static List<BoxShadow> buttonGlow = [
    BoxShadow(
      color: const Color(0xFF0E7C6B).withOpacity(0.22),
      blurRadius: 22,
      offset: const Offset(0, 10),
    ),
  ];
}

/// مقاسات موحّدة — تُستخدم بدل الأرقام المتناثرة.
class AppRadius {
  AppRadius._();
  static const double xs = 10;
  static const double sm = 14;
  static const double md = 18;
  static const double lg = 22;
  static const double xl = 28;
}

class AppSpace {
  AppSpace._();
  static const double xs = 6;
  static const double sm = 10;
  static const double md = 14;
  static const double lg = 18;
  static const double xl = 24;
}

/// ظلال ناعمة باردة (بدل الأسود/الكحلي القوي).
class AppShadows {
  AppShadows._();

  static List<BoxShadow> get card => [
        BoxShadow(
          color: const Color(0xFF0A2540).withOpacity(0.05),
          blurRadius: 20,
          offset: const Offset(0, 8),
        ),
      ];

  static List<BoxShadow> get soft => [
        BoxShadow(
          color: const Color(0xFF0A2540).withOpacity(0.035),
          blurRadius: 12,
          offset: const Offset(0, 4),
        ),
      ];
}

/// ثيم التطبيق الموحد — كل الشاشات تستخدمه تلقائيًا.
class AppTheme {
  AppTheme._();

  /// محاذاة النصوص: عربي/RTL مع كحلي داكن.
  static const TextStyle _title = TextStyle(
    color: AppColors.navy,
    fontSize: 18,
    fontWeight: FontWeight.w800,
    letterSpacing: -0.2,
    height: 1.25,
  );

  static ThemeData get light {
    final base = ThemeData(
      useMaterial3: true,
      // خط عربي مضمّن (Cairo) بدل الاعتماد على خط النظام: يضمن نفس الشكل على
      // أندرويد والويب، ويمنع ظهور النص مربّعات على المتصفح.
      fontFamily: 'Cairo',
      colorScheme: ColorScheme.fromSeed(
        seedColor: AppColors.primary,
        brightness: Brightness.light,
      ).copyWith(
        primary: AppColors.primary,
        secondary: AppColors.teal,
        surface: AppColors.surface,
        error: AppColors.red,
        onSurface: AppColors.navy,
      ),
      scaffoldBackgroundColor: AppColors.background,
      iconTheme: const IconThemeData(color: AppColors.navy, size: 22),
      appBarTheme: const AppBarTheme(
        centerTitle: true,
        elevation: 0,
        scrolledUnderElevation: 0,
        backgroundColor: AppColors.surface,
        surfaceTintColor: Colors.transparent,
        foregroundColor: AppColors.navy,
        iconTheme: IconThemeData(color: AppColors.navy, size: 22),
        titleTextStyle: _title,
      ),
      cardTheme: CardThemeData(
        elevation: 0,
        color: AppColors.surface,
        surfaceTintColor: Colors.transparent,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(AppRadius.lg)),
        margin: EdgeInsets.zero,
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: AppColors.surface,
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
        prefixIconColor: AppColors.textSecondary,
        suffixIconColor: AppColors.textSecondary,
        labelStyle: const TextStyle(color: AppColors.textSecondary, fontSize: 14),
        floatingLabelStyle: const TextStyle(color: AppColors.primary, fontWeight: FontWeight.w700),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(AppRadius.sm),
          borderSide: const BorderSide(color: AppColors.border),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(AppRadius.sm),
          borderSide: const BorderSide(color: AppColors.border),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(AppRadius.sm),
          borderSide: const BorderSide(color: AppColors.primary, width: 1.6),
        ),
        errorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(AppRadius.sm),
          borderSide: const BorderSide(color: AppColors.red),
        ),
        hintStyle: const TextStyle(color: AppColors.textSecondary, fontSize: 13.5),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          elevation: 0,
          backgroundColor: AppColors.primary,
          foregroundColor: Colors.white,
          padding: const EdgeInsets.symmetric(horizontal: 22, vertical: 14),
          minimumSize: const Size(0, 52),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(AppRadius.sm)),
          textStyle: const TextStyle(fontSize: 15, fontWeight: FontWeight.w800),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: AppColors.navy,
          minimumSize: const Size(0, 50),
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
          side: const BorderSide(color: AppColors.border, width: 1.2),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(AppRadius.sm)),
          textStyle: const TextStyle(fontSize: 14.5, fontWeight: FontWeight.w700),
        ),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          foregroundColor: AppColors.primary,
          textStyle: const TextStyle(fontSize: 14, fontWeight: FontWeight.w700),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(AppRadius.xs)),
        ),
      ),
      dialogTheme: DialogThemeData(
        backgroundColor: AppColors.surface,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(AppRadius.xl)),
        titleTextStyle: const TextStyle(fontSize: 18, fontWeight: FontWeight.w800, color: AppColors.navy),
        contentTextStyle: const TextStyle(fontSize: 14, height: 1.6, color: AppColors.textSecondary),
      ),
      bottomSheetTheme: const BottomSheetThemeData(
        backgroundColor: AppColors.surface,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        showDragHandle: true,
        dragHandleColor: AppColors.borderStrong,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(AppRadius.xl)),
        ),
      ),
      navigationBarTheme: NavigationBarThemeData(
        height: 68,
        backgroundColor: AppColors.surface,
        surfaceTintColor: Colors.transparent,
        indicatorColor: AppColors.greenTint,
        elevation: 0,
        labelTextStyle: const WidgetStatePropertyAll(
          TextStyle(fontSize: 11.5, fontWeight: FontWeight.w700, color: AppColors.navy),
        ),
      ),
      chipTheme: ChipThemeData(
        backgroundColor: AppColors.greyTint,
        selectedColor: AppColors.greenTint,
        side: BorderSide.none,
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(AppRadius.xs)),
        labelStyle: const TextStyle(fontSize: 13, fontWeight: FontWeight.w700, color: AppColors.navy),
      ),
      tabBarTheme: TabBarThemeData(
        indicatorSize: TabBarIndicatorSize.tab,
        dividerColor: Colors.transparent,
        indicator: BoxDecoration(
          color: AppColors.greenTint,
          borderRadius: BorderRadius.circular(AppRadius.xs),
        ),
        labelColor: AppColors.primary,
        unselectedLabelColor: AppColors.textSecondary,
        labelStyle: const TextStyle(fontSize: 13.5, fontWeight: FontWeight.w800),
        unselectedLabelStyle: const TextStyle(fontSize: 13.5, fontWeight: FontWeight.w600),
      ),
      checkboxTheme: CheckboxThemeData(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
        side: const BorderSide(color: AppColors.borderStrong, width: 1.4),
        fillColor: const WidgetStatePropertyAll(AppColors.primary),
      ),
      radioTheme: const RadioThemeData(
        fillColor: WidgetStatePropertyAll(AppColors.primary),
      ),
      dividerTheme: const DividerThemeData(color: AppColors.border, thickness: 1, space: 1),
      snackBarTheme: SnackBarThemeData(
        behavior: SnackBarBehavior.floating,
        backgroundColor: AppColors.ink,
        elevation: 2,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(AppRadius.sm)),
        contentTextStyle: const TextStyle(fontSize: 13.5, color: Colors.white, height: 1.4),
      ),
      progressIndicatorTheme: const ProgressIndicatorThemeData(
        color: AppColors.primary,
        linearTrackColor: AppColors.greyTint,
      ),
      listTileTheme: const ListTileThemeData(
        iconColor: AppColors.navy,
        textColor: AppColors.navy,
        titleTextStyle: TextStyle(fontSize: 14.5, fontWeight: FontWeight.w700, color: AppColors.navy),
        subtitleTextStyle: TextStyle(fontSize: 12, color: AppColors.textSecondary),
      ),
      drawerTheme: const DrawerThemeData(
        backgroundColor: AppColors.surface,
        surfaceTintColor: Colors.transparent,
        width: 288,
      ),
      sliderTheme: const SliderThemeData(
        activeTrackColor: AppColors.primary,
        thumbColor: AppColors.primary,
      ),
      switchTheme: SwitchThemeData(
        thumbColor: const WidgetStatePropertyAll(Colors.white),
        trackColor: WidgetStateProperty.resolveWith(
          (s) => s.contains(WidgetState.selected) ? AppColors.primary : AppColors.borderStrong,
        ),
      ),
    );
    return base;
  }
}
