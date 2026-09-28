import 'dart:math' as math;

import 'package:flutter/material.dart';
// show NumberFormat: بدون هذا، TextDirection الخاص بـ intl يطغى على TextDirection
// الخاص بـ Flutter (المطلوب في SalesBarChart).
import 'package:intl/intl.dart' show NumberFormat;
import 'theme.dart';

/// تنسيق الأرقام بفواصل الآلاف وأرقام لاتينية (كما في التصميم المرجعي).
class AppFmt {
  AppFmt._();
  static final NumberFormat _fmt = NumberFormat('#,##0.##', 'en');

  /// المعلمة Object? عمدًا: اسم الدالة نفسه (num) يحجب النوع المدمج `num`
  /// داخل هذا الكلاس، فلا يمكن ذكر النوع نصًا هنا.
  static String num(Object? value) {
    if (value is int) return _fmt.format(value);
    if (value is double) return _fmt.format(value);
    return _fmt.format(0);
  }

  static String money(Object? value, {String currency = 'ج.م'}) {
    if (value is int) return '${_fmt.format(value)} $currency';
    if (value is double) return '${_fmt.format(value)} $currency';
    return '0 $currency';
  }
}

/// شعار حساباتك: أعمدة بيانية صاعدة بسهم — مرسوم بالكود ليطابق المرجع
/// (أعمدة زرقاء + عمود أخضر + سهم برتقالي صاعد) داخل أيقونة بيضاء بحواف دائرية.
class HesabatakLogo extends StatelessWidget {
  const HesabatakLogo({super.key, this.size = 64});
  final double size;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(size * 0.24),
        boxShadow: [
          BoxShadow(
            color: AppColors.navy.withOpacity(0.10),
            blurRadius: 18,
            offset: const Offset(0, 6),
          ),
        ],
      ),
      padding: EdgeInsets.all(size * 0.14),
      child: CustomPaint(painter: _LogoPainter()),
    );
  }
}

class _LogoPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final w = size.width, h = size.height;
    final barW = w * 0.155;
    final r = Radius.circular(barW * 0.45);

    // الأعمدة: زرقي، أزرق، كحلي، أخضر
    final bars = [
      (Rect.fromLTWH(w * 0.10, h * 0.52, barW, h * 0.38), const Color(0xFF5B9BEA)),
      (Rect.fromLTWH(w * 0.30, h * 0.38, barW, h * 0.52), const Color(0xFF2E7CD6)),
      (Rect.fromLTWH(w * 0.50, h * 0.24, barW, h * 0.66), const Color(0xFF164E8F)),
      (Rect.fromLTWH(w * 0.70, h * 0.44, barW, h * 0.46), const Color(0xFF27A567)),
    ];
    for (final (rect, color) in bars) {
      canvas.drawRRect(RRect.fromRectAndRadius(rect, r), Paint()..color = color);
    }

    // السهم الصاعد البرتقالي
    final arrow = Paint()
      ..color = const Color(0xFFF2A93B)
      ..strokeWidth = w * 0.09
      ..strokeCap = StrokeCap.round
      ..style = PaintingStyle.stroke;
    final path = Path()
      ..moveTo(w * 0.16, h * 0.34)
      ..lineTo(w * 0.52, h * 0.10)
      ..lineTo(w * 0.66, h * 0.18);
    canvas.drawPath(path, arrow);
    // رأس السهم
    final head = Path()
      ..moveTo(w * 0.60, h * 0.06)
      ..lineTo(w * 0.70, h * 0.19)
      ..lineTo(w * 0.55, h * 0.24)
      ..close();
    canvas.drawPath(head, Paint()..color = const Color(0xFFF2A93B));
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

/// أيقونة داخل مربع ملون (نظام الأيقونات الموحد بالمرجع).
class IconTile extends StatelessWidget {
  const IconTile({
    super.key,
    required this.icon,
    required this.background,
    required this.color,
    this.size = 44,
    this.radius = 13,
  });
  final IconData icon;
  final Color background;
  final Color color;
  final double size;
  final double radius;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(radius),
      ),
      child: Icon(icon, color: color, size: size * 0.52),
    );
  }
}

/// بطاقة إحصائية للوحة الرئيسية (خلفية ملونة هادئة + أيقونة + قيمة).
class StatCard extends StatelessWidget {
  const StatCard({
    super.key,
    required this.label,
    required this.value,
    required this.icon,
    required this.background,
    required this.iconColor,
  });

  final String label;
  final String value;
  final IconData icon;
  final Color background;
  final Color iconColor;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(16),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(icon, size: 18, color: iconColor),
              const SizedBox(width: 6),
              Expanded(
                child: Text(
                  label,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(fontSize: 12, color: AppColors.textSecondary),
                ),
              ),
            ],
          ),
          const Spacer(),
          FittedBox(
            fit: BoxFit.scaleDown,
            child: Text(
              value,
              style: const TextStyle(
                fontSize: 20,
                fontWeight: FontWeight.w800,
                color: AppColors.navy,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// عنوان قسم داخل الشاشة.
class SectionHeader extends StatelessWidget {
  const SectionHeader(this.title, {super.key, this.trailing});
  final String title;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 4, bottom: 10),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(title,
              style: const TextStyle(
                  fontSize: 15, fontWeight: FontWeight.w800, color: AppColors.navy)),
          if (trailing != null) trailing!,
        ],
      ),
    );
  }
}

/// بطاقة بيضاء بحواف دائرية وظل ناعم — الحاوية القياسية لكل الأقسام.
class SectionCard extends StatelessWidget {
  const SectionCard({super.key, required this.child, this.padding});
  final Widget child;
  final EdgeInsetsGeometry? padding;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: padding ?? const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(18),
        boxShadow: [
          BoxShadow(
            color: AppColors.navy.withOpacity(0.05),
            blurRadius: 14,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: child,
    );
  }
}

/// رسم بياني أعمدة بسيط للمبيعات (بدون حزم خارجية) — كالمرجع تمامًا:
/// أعمدة زرقاء فوق خط شبكة أفقي مع قيم على المحور.
class SalesBarChart extends StatelessWidget {
  const SalesBarChart({super.key, required this.data});
  /// [(تسمية الشهر، القيمة)]
  final List<(String, double)> data;

  @override
  Widget build(BuildContext context) {
    final maxValue = data.fold<double>(1, (m, d) => m > d.$2 ? m : d.$2);
    // خطوات المحور: قيمة قريبة من العدد الجميل الأعلى.
    final step = _niceCeil(maxValue / 3);
    final steps = <double>[step, step * 2, step * 3];
    final top = steps.last;

    // المحور والأعمدة باتجاه LTR كالمرجع (الأشهر من اليسار لليمين).
    return Directionality(
      textDirection: TextDirection.ltr,
      child: Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        SizedBox(
          height: 140,
          child: Stack(
            children: [
              // خطوط الشبكة + قيمها
              Column(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: steps.reversed
                    .map((s) => Row(
                          children: [
                            SizedBox(
                              width: 44,
                              child: Text(
                                AppFmt.num(s),
                                textAlign: TextAlign.left,
                                style: const TextStyle(fontSize: 9, color: AppColors.textSecondary),
                              ),
                            ),
                            Expanded(child: Container(height: 1, color: AppColors.border)),
                          ],
                        ))
                    .toList(),
              ),
              // الأعمدة
              PositionedDirectional(
                start: 52,
                end: 0,
                top: 0,
                bottom: 0,
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: data.map((d) {
                    final ratio = top == 0 ? 0.0 : (d.$2 / top).clamp(0.02, 1.0);
                    return Expanded(
                      child: Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 5),
                        child: Align(
                          alignment: Alignment.bottomCenter,
                          child: FractionallySizedBox(
                            heightFactor: ratio,
                            child: Container(
                              decoration: BoxDecoration(
                                gradient: const LinearGradient(
                                  begin: Alignment.topCenter,
                                  end: Alignment.bottomCenter,
                                  colors: [Color(0xFF5B9BEA), Color(0xFF1565C0)],
                                ),
                                borderRadius: const BorderRadius.vertical(top: Radius.circular(6)),
                              ),
                            ),
                          ),
                        ),
                      ),
                    );
                  }).toList(),
                ),
              ),
            ],
          ),
        ),
        const SizedBox(height: 6),
        Row(
          children: [
            const SizedBox(width: 52),
            Expanded(
              child: Row(
                children: data
                    .map((d) => Expanded(
                          child: Text(
                            d.$1,
                            textAlign: TextAlign.center,
                            style: const TextStyle(fontSize: 10, color: AppColors.textSecondary),
                          ),
                        ))
                    .toList(),
              ),
            ),
          ],
        ),
      ],
    );
  }

  double _niceCeil(double v) {
    if (v <= 0) return 1;
    final mag = math.pow(10, (math.log(v) / math.ln10).floor()).toDouble();
    final norm = v / mag;
    final nice = norm <= 1 ? 1.0 : (norm <= 2 ? 2.0 : (norm <= 5 ? 5.0 : 10.0));
    return nice * mag;
  }
}

/// صف قائمة قياسي (أيقونة + عنوان + سطر فرعي + رصيد + سهم).
class AppListTile extends StatelessWidget {
  const AppListTile({
    super.key,
    required this.icon,
    required this.title,
    required this.subtitle,
    this.trailingLabel,
    this.trailingColor,
    this.onTap,
    this.trailingChevron = true,
  });

  final IconData icon;
  final String title;
  final String subtitle;
  final String? trailingLabel;
  final Color? trailingColor;
  final VoidCallback? onTap;
  final bool trailingChevron;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      borderRadius: BorderRadius.circular(14),
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 10),
        child: Row(
          children: [
            IconTile(icon: icon, background: AppColors.blueTint, color: AppColors.primary, size: 42),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(fontSize: 14.5, fontWeight: FontWeight.w700, color: AppColors.navy)),
                  const SizedBox(height: 2),
                  Text(subtitle,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(fontSize: 12, color: AppColors.textSecondary)),
                ],
              ),
            ),
            if (trailingLabel != null) ...[
              const SizedBox(width: 8),
              Text(
                trailingLabel!,
                style: TextStyle(
                  fontSize: 13.5,
                  fontWeight: FontWeight.w800,
                  color: trailingColor ?? AppColors.navy,
                ),
              ),
            ],
            if (trailingChevron) ...[
              const SizedBox(width: 4),
              const Icon(Icons.chevron_left, color: AppColors.textSecondary),
            ],
          ],
        ),
      ),
    );
  }
}

/// صف داخل جدول البنود.
class ItemRow extends StatelessWidget {
  const ItemRow({
    super.key,
    required this.onDelete,
    required this.child,
  });
  final VoidCallback onDelete;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // في RTL تظهر أيقونة الحذف في بداية الصف (يمين) كالمرجع.
          IconButton(
            visualDensity: VisualDensity.compact,
            icon: const Icon(Icons.delete_outline, color: AppColors.red, size: 20),
            onPressed: onDelete,
          ),
          Expanded(child: child),
        ],
      ),
    );
  }
}

/// صف ملخص (تسمية + قيمة) يُستخدم في الفواتير والتقارير.
class SummaryRow extends StatelessWidget {
  const SummaryRow({
    super.key,
    required this.label,
    required this.value,
    this.emphasized = false,
    this.valueColor,
  });
  final String label;
  final String value;
  final bool emphasized;
  final Color? valueColor;

  @override
  Widget build(BuildContext context) {
    final style = emphasized
        ? const TextStyle(fontSize: 15, fontWeight: FontWeight.w800, color: AppColors.navy)
        : const TextStyle(fontSize: 13.5, color: AppColors.textSecondary);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label, style: style),
          Text(value,
              style: TextStyle(
                fontSize: emphasized ? 16 : 14,
                fontWeight: FontWeight.w800,
                color: valueColor ?? AppColors.navy,
              )),
        ],
      ),
    );
  }
}

/// القائمة الجانبية (RTL) — شعار + كل الأقسام + الملف الشخصي أسفلها.
class AppDrawer extends StatelessWidget {
  const AppDrawer({
    super.key,
    required this.sections,
    required this.current,
    required this.onSelect,
    required this.userName,
    required this.companyName,
    required this.onLogout,
  });

  /// أقسام التطبيق: (عنوان، أيقونة)
  final List<(String, IconData)> sections;
  final String current;
  final ValueChanged<String> onSelect;
  final String userName;
  final String companyName;
  final VoidCallback onLogout;

  @override
  Widget build(BuildContext context) {
    return Drawer(
      backgroundColor: Colors.white,
      // In RTL the drawer opens from the end (visually left), so the rounded
      // edge faces the screen's left side and the hinge stays flat.
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.horizontal(left: Radius.circular(20)),
      ),
      child: SafeArea(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 18, 20, 8),
              child: Row(
                children: [
                  const HesabatakLogo(size: 44),
                  const SizedBox(width: 10),
                  const Text('حساباتك',
                      style: TextStyle(fontSize: 20, fontWeight: FontWeight.w800, color: AppColors.navy)),
                ],
              ),
            ),
            const Divider(),
            Expanded(
              child: ListView(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                children: [
                  for (final (title, icon) in sections)
                    _DrawerItem(
                      title: title,
                      icon: icon,
                      color: _colorFor(title),
                      active: title == current,
                      onTap: () {
                        Navigator.of(context).pop();
                        onSelect(title);
                      },
                    ),
                ],
              ),
            ),
            const Divider(),
            ListTile(
              leading: const CircleAvatar(
                backgroundColor: AppColors.blueTint,
                child: Icon(Icons.person, color: AppColors.primary),
              ),
              title: Text(userName,
                  style: const TextStyle(fontWeight: FontWeight.w700, color: AppColors.navy)),
              subtitle: Text(companyName, style: const TextStyle(fontSize: 12)),
              trailing: IconButton(
                tooltip: 'تسجيل الخروج',
                icon: const Icon(Icons.logout, color: AppColors.red),
                onPressed: onLogout,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _DrawerItem extends StatelessWidget {
  const _DrawerItem({
    required this.title,
    required this.icon,
    required this.color,
    required this.active,
    required this.onTap,
  });
  final String title;
  final IconData icon;
  final Color color;
  final bool active;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.symmetric(vertical: 2),
      decoration: BoxDecoration(
        color: active ? AppColors.blueTint : Colors.transparent,
        borderRadius: BorderRadius.circular(12),
      ),
      child: ListTile(
        dense: true,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
        leading: Icon(icon, color: color),
        title: Text(
          title,
          style: TextStyle(
            fontSize: 14,
            fontWeight: active ? FontWeight.w800 : FontWeight.w600,
            color: active ? AppColors.primary : AppColors.navy,
          ),
        ),
        onTap: onTap,
      ),
    );
  }
}

/// لون كل قسم في القائمة الجانبية (نظام الأيقونات الملون).
Color _colorFor(String section) {
  switch (section) {
    case 'الرئيسية':
      return AppColors.primary;
    case 'المبيعات':
      return AppColors.amber;
    case 'المشتريات':
      return AppColors.teal;
    case 'المصروفات':
      return AppColors.red;
    case 'العملاء':
      return AppColors.primary;
    case 'الموردون':
      return AppColors.amber;
    case 'المخزون':
      return AppColors.amber;
    case 'الخزنة والبنك':
      return AppColors.primary;
    case 'الأصول الثابتة':
      return AppColors.green;
    case 'التقارير':
      return AppColors.primary;
    case 'الإعدادات':
      return AppColors.textSecondary;
    default:
      return AppColors.primary;
  }
}
