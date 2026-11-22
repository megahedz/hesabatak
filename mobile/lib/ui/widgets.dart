import 'dart:math' as math;

import 'package:flutter/material.dart';
// show NumberFormat: بدون هذا، TextDirection الخاص بـ intl يطغى على TextDirection
// الخاص بـ Flutter (المطلوب في SalesBarChart).
import 'package:intl/intl.dart' show NumberFormat;
import '../core/app_config.dart';
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

/// زر عصري بتدرّج بنفسجي → أزرق → سيان حول نواة كحلية داكنة (نمط Uiverse).
/// على الويب/الديسكتوب تختفي النواة عند مرور الماوس فيظهر التدرّج كاملًا،
/// والضغط يصغّر الزر قليلًا — نفس إحساس الـ CSS المرجعي.
class GradientButton extends StatefulWidget {
  const GradientButton({
    super.key,
    required this.onPressed,
    required this.child,
    this.icon,
    this.loading = false,
    this.expand = false,
    this.height = 52,
    this.colors = AppGradients.button,
    this.compact = false,
  });

  const GradientButton.icon({
    super.key,
    required this.onPressed,
    required Widget this.icon,
    required Widget label,
    this.loading = false,
    this.expand = false,
    this.height = 52,
    this.colors = AppGradients.button,
    this.compact = false,
  }) : child = label;

  final VoidCallback? onPressed;
  final Widget child;
  final Widget? icon;
  final bool loading;
  final bool expand;
  final double height;
  final List<Color> colors;
  final bool compact;

  @override
  State<GradientButton> createState() => _GradientButtonState();
}

class _GradientButtonState extends State<GradientButton> {
  bool _hover = false;
  bool _pressed = false;

  @override
  Widget build(BuildContext context) {
    final enabled = widget.onPressed != null && !widget.loading;
    final radius = widget.compact ? 12.0 : 14.0;

    // Wrap بدل Row: لا يحتاج عرضًا محددًا (يعمل داخل نوافذ الحوار والصفوف
    // والأعمدة الممتدة على حد سواء) ويلف النص الطويل بدل أن يفيض.
    final content = Wrap(
      alignment: WrapAlignment.center,
      crossAxisAlignment: WrapCrossAlignment.center,
      spacing: widget.compact ? 6 : 9,
      runSpacing: 4,
      children: [
        if (widget.loading)
          const SizedBox(
            width: 17,
            height: 17,
            child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
          )
        else if (widget.icon != null)
          IconTheme.merge(
            data: IconThemeData(color: Colors.white, size: widget.compact ? 17 : 20),
            child: widget.icon!,
          ),
        DefaultTextStyle.merge(
          style: TextStyle(
            color: Colors.white,
            fontSize: widget.compact ? 13 : 15.5,
            fontWeight: FontWeight.w800,
            height: 1.2,
          ),
          child: IconTheme.merge(
            data: const IconThemeData(color: Colors.white),
            child: widget.child,
          ),
        ),
      ],
    );

    // سطح واحد متدرّج بلون غامق كفاية (زمردي): الأبيض عليه 4.6:1 أو أفضل،
    // فما احتجاناش لطبقة كحلية داخلية. التفاعل يظهر بطبقة بيضاء 8% عند الهوفر
    // وبطبقة داكنة 12% مع تصغير خفيف عند الضغط — بدون أي تغيير في التباين.
    Widget body = AnimatedContainer(
      duration: const Duration(milliseconds: 180),
      curve: Curves.easeOut,
      constraints: BoxConstraints(minHeight: widget.height),
      padding: EdgeInsets.symmetric(
        horizontal: widget.compact ? 16 : 22,
        vertical: widget.compact ? 4 : 8,
      ),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.centerRight,
          end: Alignment.centerLeft,
          colors: _pressed && enabled
              ? widget.colors.map((c) => Color.lerp(c, Colors.black, 0.12)!).toList()
              : widget.colors,
        ),
        borderRadius: BorderRadius.circular(radius),
        boxShadow: widget.colors == AppGradients.button && enabled
            ? AppGradients.buttonGlow
            : null,
      ),
      // Center بعوامل 1 يلفّ المحتوى بحجمه الطبيعي (بدل التمدد لعرض الحاوية)
      // مع توسيطه رأسيًا داخل minHeight — فأزرار الحوار تبقى بعرض نصّها لا
      // بعرض النافذة، والأزرار الممتدة يحددها expand.
      child: Center(
        widthFactor: 1,
        heightFactor: 1,
        child: Stack(
          alignment: Alignment.center,
          children: [
            Positioned.fill(
              child: IgnorePointer(
                child: AnimatedOpacity(
                  opacity: _hover && enabled ? 1 : 0,
                  duration: const Duration(milliseconds: 160),
                  child: DecoratedBox(
                    decoration: BoxDecoration(
                      color: Colors.white.withOpacity(0.10),
                      borderRadius: BorderRadius.circular(radius),
                    ),
                  ),
                ),
              ),
            ),
            content,
          ],
        ),
      ),
    );

    body = AnimatedScale(
      scale: _pressed ? 0.98 : 1,
      duration: const Duration(milliseconds: 110),
      // التحميل يخفض الشفافية قليلًا فقط: النص «جارٍ تسجيل الدخول…» يبقى مقروءًا.
      child: Opacity(
        opacity: enabled ? 1 : (widget.loading ? 0.9 : 0.5),
        child: body,
      ),
    );

    body = Semantics(
      button: true,
      enabled: enabled,
      child: MouseRegion(
        cursor: enabled ? SystemMouseCursors.click : SystemMouseCursors.basic,
        onEnter: (_) => setState(() => _hover = true),
        onExit: (_) => setState(() {
          _hover = false;
          _pressed = false;
        }),
        child: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTapDown: enabled ? (_) => setState(() => _pressed = true) : null,
          onTapUp: enabled ? (_) => setState(() => _pressed = false) : null,
          onTapCancel: enabled ? () => setState(() => _pressed = false) : null,
          onTap: enabled ? widget.onPressed : null,
          child: body,
        ),
      ),
    );

    if (!widget.expand) return body;
    return SizedBox(width: double.infinity, child: body);
  }
}

/// شعار حساباتك — نفس علامة أيقونة التطبيق، مرسومة مباشرة بـ Canvas بدل
/// تحميل صورة: يطابق الأيقونة تمامًا، ولا يتعلق ظهوره بتحميل/فكّ ضغط صورة
/// (كان يظهر مربّعًا أبيض على بعض المتصفحات).
class HesabatakLogo extends StatelessWidget {
  const HesabatakLogo({super.key, this.size = 64});
  final double size;

  @override
  Widget build(BuildContext context) {
    final radius = size * 0.26;
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(radius),
        boxShadow: [
          BoxShadow(
            color: AppColors.navy.withOpacity(0.18),
            blurRadius: size * 0.22,
            offset: Offset(0, size * 0.07),
          ),
        ],
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(radius),
        child: CustomPaint(size: Size.square(size), painter: _LogoPainter(radius)),
      ),
    );
  }
}

class _LogoPainter extends CustomPainter {
  _LogoPainter(this.radius);
  final double radius;

  // الرسم موصوف على شبكة 1024 ثم يُقاس على المقاس المطلوب.
  static const double _grid = 1024;

  @override
  void paint(Canvas canvas, Size size) {
    final s = size.width / _grid;
    final rect = Offset.zero & size;
    final rrect = RRect.fromRectAndRadius(rect, Radius.circular(radius));

    canvas.drawRRect(
      rrect,
      Paint()
        ..shader = const LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [Color(0xFF0A2540), Color(0xFF0D4E5A), Color(0xFF0E7C6B)],
        ).createShader(rect),
    );
    canvas.save();
    canvas.clipRRect(rrect);

    // الأعمدة الصاعدة
    const barW = 126.0, gap = 58.0, baseY = 752.0;
    const heights = [240.0, 386.0, 526.0];
    const opacities = [0.59, 0.80, 0.96];
    final groupLeft = (_grid - (3 * barW + 2 * gap)) / 2;
    for (var i = 0; i < 3; i++) {
      final left = (groupLeft + i * (barW + gap)) * s;
      final top = (baseY - heights[i]) * s;
      final bar = RRect.fromRectAndRadius(
        Rect.fromLTRB(left, top, left + barW * s, baseY * s),
        Radius.circular(34 * s),
      );
      canvas.drawRRect(bar, Paint()..color = Colors.white.withOpacity(opacities[i]));
    }

    // سهم النمو
    final start = Offset(238 * s, 556 * s);
    final end = Offset(792 * s, 296 * s);
    final arrow = Paint()
      ..color = const Color(0xFF7FE9C3)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 56 * s
      ..strokeCap = StrokeCap.round;
    canvas.drawLine(start, end, arrow);

    final dir = end - start;
    final len = dir.distance;
    final u = dir / len;
    final perp = Offset(-u.dy, u.dx);
    final headLen = 150 * s, headHalf = 108 * s;
    final head = Path()
      ..moveTo(end.dx + u.dx * 6 * s, end.dy + u.dy * 6 * s)
      ..lineTo(end.dx - u.dx * headLen + perp.dx * headHalf, end.dy - u.dy * headLen + perp.dy * headHalf)
      ..lineTo(end.dx - u.dx * headLen - perp.dx * headHalf, end.dy - u.dy * headLen - perp.dy * headHalf)
      ..close();
    canvas.drawPath(head, Paint()..color = const Color(0xFF7FE9C3));

    canvas.restore();
  }

  @override
  bool shouldRepaint(covariant _LogoPainter old) => old.radius != radius;
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
        border: Border.all(color: color.withOpacity(0.10), width: 1),
      ),
      child: Icon(icon, color: color, size: size * 0.50),
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
    // بطاقة بيضاء نظيفة: اللون يبقى في بلاطة الأيقونة فقط، فيظل الجدول الرقمي
    // هادئًا وقروءًا، ويُقرأ الرقم قبل الزينة.
    return Container(
      padding: const EdgeInsets.fromLTRB(13, 13, 13, 12),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(AppRadius.md),
        border: Border.all(color: AppColors.border),
        boxShadow: AppShadows.soft,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Text(
                  label,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    fontSize: 11.5,
                    height: 1.3,
                    fontWeight: FontWeight.w600,
                    color: AppColors.textSecondary,
                  ),
                ),
              ),
              const SizedBox(width: 6),
              IconTile(icon: icon, background: background, color: iconColor, size: 32, radius: 10),
            ],
          ),
          const SizedBox(height: 12),
          FittedBox(
            fit: BoxFit.scaleDown,
            alignment: AlignmentDirectional.centerStart,
            child: Text(
              value,
              style: const TextStyle(
                fontSize: 21,
                fontWeight: FontWeight.w800,
                letterSpacing: -0.5,
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
      padding: const EdgeInsets.only(top: 2, bottom: 12),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Flexible(
            child: Text(
              title,
              style: const TextStyle(
                fontSize: 15,
                fontWeight: FontWeight.w800,
                letterSpacing: -0.2,
                color: AppColors.navy,
              ),
            ),
          ),
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
      padding: padding ?? const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(AppRadius.lg),
        border: Border.all(color: AppColors.border),
        boxShadow: AppShadows.card,
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
      ),
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
      borderRadius: BorderRadius.circular(AppRadius.sm),
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 9),
        child: Row(
          children: [
            IconTile(icon: icon, background: AppColors.greenTint, color: AppColors.primary, size: 40, radius: 12),
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
              const SizedBox(width: 6),
              const Icon(Icons.chevron_left_rounded, size: 20, color: AppColors.textSecondary),
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
      backgroundColor: AppColors.surface,
      // In RTL the drawer opens from the end (visually left), so the rounded
      // edge faces the screen's left side and the hinge stays flat.
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.horizontal(left: Radius.circular(AppRadius.xl)),
      ),
      child: SafeArea(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // ===== هوية المشروع =====
            Container(
              margin: const EdgeInsets.fromLTRB(12, 12, 12, 8),
              padding: const EdgeInsets.fromLTRB(14, 16, 14, 16),
              decoration: BoxDecoration(
                gradient: AppGradients.brandGradient,
                borderRadius: BorderRadius.circular(AppRadius.lg),
                boxShadow: [
                  BoxShadow(
                    color: AppColors.primary.withOpacity(0.24),
                    blurRadius: 24,
                    offset: const Offset(0, 10),
                  ),
                ],
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      const HesabatakLogo(size: 42),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Text('حساباتك',
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: TextStyle(
                                    fontSize: 18, fontWeight: FontWeight.w800, color: Colors.white)),
                            const SizedBox(height: 2),
                            Text(
                              companyName.isEmpty ? 'حسابات مشروعك' : companyName,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: TextStyle(fontSize: 11.5, color: Colors.white.withOpacity(0.78)),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 14),
                  Row(
                    children: [
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
                        decoration: BoxDecoration(
                          color: Colors.white.withOpacity(0.14),
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: Text(
                          'إصدار ${AppConfig.appVersion}',
                          style: const TextStyle(
                              fontSize: 10.5, fontWeight: FontWeight.w700, color: Colors.white),
                        ),
                      ),
                      const SizedBox(width: 8),
                      Text(userName,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                              fontSize: 11.5,
                              fontWeight: FontWeight.w700,
                              color: Colors.white.withOpacity(0.9))),
                    ],
                  ),
                ],
              ),
            ),
            Expanded(
              child: ListView(
                padding: const EdgeInsets.fromLTRB(10, 6, 10, 6),
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
            Padding(
              padding: const EdgeInsets.fromLTRB(12, 4, 12, 12),
              child: Container(
                decoration: BoxDecoration(
                  color: AppColors.background,
                  borderRadius: BorderRadius.circular(AppRadius.md),
                  border: Border.all(color: AppColors.border),
                ),
                child: ListTile(
                  dense: true,
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(AppRadius.md)),
                  leading: const CircleAvatar(
                    radius: 17,
                    backgroundColor: AppColors.greenTint,
                    child: Icon(Icons.person_outline_rounded, size: 19, color: AppColors.primary),
                  ),
                  title: Text(userName,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 13.5)),
                  subtitle: const Text('تسجيل الخروج من الحساب', style: TextStyle(fontSize: 11)),
                  trailing: IconButton(
                    tooltip: 'تسجيل الخروج',
                    icon: const Icon(Icons.logout_rounded, size: 19, color: AppColors.red),
                    onPressed: onLogout,
                  ),
                  onTap: onLogout,
                ),
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
      margin: const EdgeInsets.symmetric(vertical: 1.5),
      decoration: BoxDecoration(
        color: active ? AppColors.greenTint : Colors.transparent,
        borderRadius: BorderRadius.circular(AppRadius.sm),
      ),
      child: InkWell(
        borderRadius: BorderRadius.circular(AppRadius.sm),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 7),
          child: Row(
            children: [
              IconTile(
                icon: icon,
                background: active ? Colors.white : color.withOpacity(0.10),
                color: color,
                size: 34,
                radius: 10,
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Text(
                  title,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontSize: 13.5,
                    fontWeight: active ? FontWeight.w800 : FontWeight.w600,
                    color: active ? AppColors.primary : AppColors.navy,
                  ),
                ),
              ),
              if (active)
                Container(
                  width: 6,
                  height: 6,
                  decoration: const BoxDecoration(
                    color: AppColors.primary,
                    shape: BoxShape.circle,
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

/// لون كل قسم في القائمة الجانبية (نظام الأيقونات الملون).
Color _colorFor(String section) {
  // لون واحد لكل مجموعة منطقية: أموال داخلة (أخضر)، خارجة (أحمر)،
  // أطراف (أزرق/بنفسجي)، وبنية تحتية (رمادي) — بدل عشوائية الألوان.
  switch (section) {
    case 'الرئيسية':
      return AppColors.primary;
    case 'المبيعات':
      return AppColors.greenDark;
    case 'المشتريات':
      return AppColors.purple;
    case 'المصروفات':
      return AppColors.red;
    case 'العملاء':
      return const Color(0xFF1E6FD9);
    case 'الموردون':
      return AppColors.purple;
    case 'الأصناف':
      return AppColors.amber;
    case 'الخزنة والبنك':
      return const Color(0xFF1E6FD9);
    case 'الأصول الثابتة':
      return AppColors.teal;
    case 'التقارير':
      return AppColors.primary;
    case 'الإعدادات':
      return AppColors.textSecondary;
    default:
      return AppColors.primary;
  }
}
