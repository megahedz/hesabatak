import 'package:flutter/material.dart';
import 'package:file_picker/file_picker.dart';
import '../../core/api_client.dart';
import '../../core/app_config.dart';
import '../../core/session.dart';
import '../../ui/theme.dart';
import '../../ui/widgets.dart';
import '../home/home_shell.dart';
import '../notifications/notifications_sheet.dart';
import '../operations/quick_actions_sheet.dart';
import '../reports/export_service.dart';
import 'dashboard_model.dart';

/// الرئيسية — نفس تخطيط المرجع: اختيار الفترة، 4 بطاقات أرقام الفترة
/// (مبيعات/مشتريات/مصروفات/صافي الربح)، 4 بطاقات أرصدة (خزينة/بنك/عملاء/
/// موردين)، ثم رسم بياني للمبيعات آخر 6 أشهر، وأخيرًا العمليات السريعة.
class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  final _api = ApiClient(baseUrl: AppConfig.apiBaseUrl);
  late Future<DashboardData> _future;

  /// بداية الفترة المختارة (null = الشهر الحالي).
  DateTime? _periodStart;

  static const _periods = <(String, int?)>[
    ('هذا الشهر', null),
    ('آخر 3 أشهر', 3),
    ('آخر 6 أشهر', 6),
    ('هذا العام', 12),
  ];
  String _periodLabel = 'هذا الشهر';

  @override
  void initState() {
    super.initState();
    _load();
    // بعد أي عملية سريعة من البار السفلي: أعد تحميل الأرقام فورًا.
    HomeShell.onSectionRefresh = (_) => _reload();
  }

  void _load() {
    setState(() {
      _future = _api.getDashboard(AppConfig.companyId, periodStart: _periodStart).then(DashboardData.fromJson);
    });
  }

  void _reload() => _load();

  Future<void> _pickPeriod() async {
    final picked = await showModalBottomSheet<String>(
      context: context,
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(20))),
      builder: (ctx) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            for (final (label, months) in _periods)
              ListTile(
                title: Text(label, textAlign: TextAlign.center),
                trailing: label == _periodLabel ? const Icon(Icons.check, color: AppColors.primary) : null,
                onTap: () => Navigator.of(ctx).pop(label),
              ),
          ],
        ),
      ),
    );
    if (picked == null || picked == _periodLabel) return;
    final found = _periods.firstWhere((p) => p.$1 == picked);
    final months = found.$2;
    setState(() {
      _periodLabel = picked;
      _periodStart = months == null ? null : _monthsAgo(months);
    });
    _load();
  }

  static DateTime _monthsAgo(int n) {
    final now = DateTime.now();
    var m = now.month - n + 1, y = now.year;
    while (m <= 0) {
      m += 12;
      y -= 1;
    }
    return DateTime(y, m, 1);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppHeader(
        title: 'حساباتك',
        actions: [
          IconButton(
            tooltip: 'التنبيهات',
            icon: const Icon(Icons.notifications_outlined, color: AppColors.navy),
            onPressed: () => showNotificationsSheet(context),
          ),
        ],
      ),
      body: FutureBuilder<DashboardData>(
        future: _future,
        builder: (context, snapshot) {
          if (snapshot.connectionState != ConnectionState.done) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snapshot.hasError) {
            // Friendly Arabic message, not the raw exception (spec §49).
            return _ErrorState(onRetry: _reload);
          }
          final data = snapshot.data!;
          return RefreshIndicator(
            onRefresh: () async => _reload(),
            color: AppColors.primary,
            child: ListView(
              padding: const EdgeInsets.all(16),
              children: [
                // ===== اختيار الفترة =====
                GestureDetector(
                  onTap: _pickPeriod,
                  child: SectionCard(
                    padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Row(
                          children: [
                            const Icon(Icons.calendar_month_outlined, size: 18, color: AppColors.primary),
                            const SizedBox(width: 8),
                            Text(_periodLabel,
                                style: const TextStyle(
                                    fontSize: 14, fontWeight: FontWeight.w700, color: AppColors.navy)),
                          ],
                        ),
                        const Icon(Icons.keyboard_arrow_down_rounded, color: AppColors.textSecondary),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 14),

                // ===== بطاقات الفترة =====
                Row(
                  children: [
                    Expanded(
                      child: StatCard(
                        label: 'إجمالي المبيعات',
                        value: AppFmt.num(data.periodSales),
                        icon: Icons.payments_rounded,
                        background: AppColors.greenTint,
                        iconColor: AppColors.green,
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: StatCard(
                        label: 'إجمالي المشتريات',
                        value: AppFmt.num(data.periodPurchases),
                        icon: Icons.shopping_cart_rounded,
                        background: AppColors.blueTint,
                        iconColor: AppColors.primary,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 10),
                Row(
                  children: [
                    Expanded(
                      child: StatCard(
                        label: 'إجمالي المصروفات',
                        value: AppFmt.num(data.periodExpenses),
                        icon: Icons.account_balance_wallet_rounded,
                        background: AppColors.redTint,
                        iconColor: AppColors.red,
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: StatCard(
                        label: 'صافي الربح',
                        value: AppFmt.num(data.netProfit),
                        icon: Icons.trending_up_rounded,
                        background: AppColors.amberTint,
                        iconColor: AppColors.amber,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 14),

                // ===== الأرصدة =====
                Row(
                  children: [
                    Expanded(
                      child: StatCard(
                        label: 'رصيد الخزينة',
                        value: AppFmt.num(data.cashBalance),
                        icon: Icons.savings_rounded,
                        background: AppColors.purpleTint,
                        iconColor: AppColors.purple,
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: StatCard(
                        label: 'رصيد البنك',
                        value: AppFmt.num(data.bankBalance),
                        icon: Icons.account_balance_rounded,
                        background: AppColors.blueTint,
                        iconColor: AppColors.primary,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 10),
                Row(
                  children: [
                    Expanded(
                      child: StatCard(
                        label: 'أرصدة العملاء (لنا)',
                        value: AppFmt.num(data.receivableFromCustomers),
                        icon: Icons.groups_rounded,
                        background: AppColors.tealTint,
                        iconColor: AppColors.teal,
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: StatCard(
                        label: 'أرصدة الموردين (علينا)',
                        value: AppFmt.num(data.payableToSuppliers),
                        icon: Icons.storefront_rounded,
                        background: AppColors.amberTint,
                        iconColor: AppColors.amber,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 18),

                // ===== رسم المبيعات =====
                SectionCard(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const SectionHeader('المبيعات خلال الأشهر الماضية'),
                      SalesBarChart(data: data.salesSeries),
                    ],
                  ),
                ),
                const SizedBox(height: 18),

                // ===== عمليات سريعة =====
                SectionCard(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const SectionHeader('عمليات سريعة'),
                      _QuickActionsGrid(onDone: _reload),
                    ],
                  ),
                ),
                const SizedBox(height: 8),
              ],
            ),
          );
        },
      ),
    );
  }
}

class _QuickActionsGrid extends StatelessWidget {
  const _QuickActionsGrid({required this.onDone});
  final VoidCallback onDone;

  // لون مميز لكل عملية — تمايز بصري أسرع من لون موحد.
  // (label, icon, bg, fg) — parallel lists بدل records لتفادي أي اختلاف إصدار.
  static const _labels = ['بيع', 'شراء', 'قبض من عميل', 'دفع لمورد', 'مصروف', 'إيداع رأس مال', 'سحب شخصي', 'تحويل بين الحسابات'];
  static const _icons = [
    Icons.point_of_sale_rounded,
    Icons.shopping_cart_rounded,
    Icons.north_rounded,
    Icons.south_rounded,
    Icons.receipt_long_rounded,
    Icons.add_business_rounded,
    Icons.person_remove_rounded,
    Icons.swap_horiz_rounded,
  ];
  static const _bgs = [
    AppColors.greenTint,
    AppColors.blueTint,
    AppColors.tealTint,
    AppColors.amberTint,
    AppColors.redTint,
    AppColors.purpleTint,
    AppColors.greyTint,
    AppColors.blueTint,
  ];
  static const _fgs = [
    AppColors.green,
    AppColors.primary,
    AppColors.teal,
    AppColors.amber,
    AppColors.red,
    AppColors.purple,
    AppColors.navy,
    AppColors.primary,
  ];

  @override
  Widget build(BuildContext context) {
    return GridView.count(
      crossAxisCount: 4,
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      crossAxisSpacing: 8,
      mainAxisSpacing: 12,
      childAspectRatio: 0.85,
      children: [for (var i = 0; i < _labels.length; i++) InkWell(
          borderRadius: BorderRadius.circular(12),
          onTap: () => showQuickActionSheet(context, action: _labels[i], onDone: onDone),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              IconTile(
                icon: _icons[i],
                background: _bgs[i],
                color: _fgs[i],
                size: 46,
              ),
              const SizedBox(height: 6),
              Text(_labels[i],
                  textAlign: TextAlign.center,
                  maxLines: 2,
                  style: const TextStyle(fontSize: 10.5, color: AppColors.navy)),
            ],
          ),
        ),
      ]
    );
  }
}

class _ErrorState extends StatelessWidget {
  const _ErrorState({required this.onRetry});
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Text('تعذر تحميل البيانات. تأكد من الاتصال وحاول مرة أخرى.',
              textAlign: TextAlign.center,
              style: TextStyle(color: AppColors.textSecondary)),
          const SizedBox(height: 12),
          FilledButton(onPressed: onRetry, child: const Text('إعادة المحاولة')),
        ],
      ),
    );
  }
}

// ======================================================================
// Phase 6: backup & restore (spec §59/§60) — now reachable from الإعدادات
// ======================================================================

/// Bottom sheet with: download a full backup (JSON, shareable anywhere),
/// and restore from a previously saved backup file (replace mode, with a
/// typed confirmation because it overwrites everything).
Future<void> showBackupSheet(BuildContext context) async {
  final api = ApiClient(baseUrl: AppConfig.apiBaseUrl);
  await showModalBottomSheet(
    context: context,
    shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(20))),
    builder: (sheetContext) => SafeArea(
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text('النسخ الاحتياطي والاستعادة',
                style: TextStyle(fontSize: 20, fontWeight: FontWeight.w800, color: AppColors.navy)),
            const SizedBox(height: 8),
            const Text('خذ نسخة كاملة من بيانات مشروعك، أو استعد نسخة سابقة. الاستعادة تستبدل كل البيانات الحالية.',
                style: TextStyle(color: AppColors.textSecondary, fontSize: 13)),
            const SizedBox(height: 16),
            FilledButton.icon(
              icon: const Icon(Icons.download_outlined),
              label: const Text('تنزيل نسخة احتياطية'),
              onPressed: () async {
                Navigator.of(sheetContext).pop();
                final messenger = ScaffoldMessenger.of(context);
                try {
                  messenger.showSnackBar(const SnackBar(content: Text('جارٍ تجهيز النسخة الاحتياطية…')));
                  final file = await api.downloadBackup();
                  if (!context.mounted) return;
                  await shareBackupFile(context, file.bytes, file.fileName);
                } on ApiNetworkException {
                  messenger.showSnackBar(const SnackBar(
                      content: Text('تعذر تنزيل النسخة. تأكد من الاتصال وحاول مرة أخرى.')));
                } catch (_) {
                  messenger.showSnackBar(const SnackBar(
                      content: Text('تعذر تنزيل النسخة الاحتياطية. حاول مرة أخرى.')));
                }
              },
            ),
            const SizedBox(height: 8),
            OutlinedButton.icon(
              icon: const Icon(Icons.restore),
              label: const Text('استعادة من ملف'),
              onPressed: () async {
                Navigator.of(sheetContext).pop();
                await _restoreFromPicker(context, api);
              },
            ),
          ],
        ),
      ),
    ),
  );
}

Future<void> _restoreFromPicker(BuildContext context, ApiClient api) async {
  final picked = await FilePicker.platform.pickFiles(
    type: FileType.custom,
    allowedExtensions: ['json'],
    withData: true,
  );
  if (picked == null || picked.files.single.bytes == null) return;
  if (!context.mounted) return;

  // Replace mode is destructive — require an explicit typed confirmation.
  String restoreText = '';
  final confirmed = await showDialog<bool>(
    context: context,
    builder: (dialogContext) => Directionality(
      textDirection: TextDirection.rtl,
      child: AlertDialog(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
        title: const Text('تأكيد الاستعادة'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('سيتم استبدال كل بيانات المشروع الحالية ببيانات النسخة الاحتياطية. لا يمكن التراجع عن هذه الخطوة.'),
            const SizedBox(height: 12),
            TextField(
              keyboardType: TextInputType.text,
              decoration: const InputDecoration(
                labelText: 'اكتب «استعادة» للتأكيد',
              ),
              onChanged: (v) => restoreText = v,
            ),
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.of(dialogContext).pop(false), child: const Text('إلغاء')),
          FilledButton(
            onPressed: () => Navigator.of(dialogContext).pop(restoreText.trim() == 'استعادة'),
            child: const Text('استعادة'),
          ),
        ],
      ),
    ),
  );
  if (confirmed != true || !context.mounted) return;

  final messenger = ScaffoldMessenger.of(context);
  try {
    await api.restoreBackup(picked.files.single.bytes!);
    messenger.showSnackBar(const SnackBar(content: Text('تمت الاستعادة بنجاح')));
  } on ApiException catch (e) {
    messenger.showSnackBar(SnackBar(
        content: Text(e.statusCode == 400
            ? 'الملف غير صالح للاستعادة — تأكد أنه نسخة احتياطية من حساباتك.'
            : 'تعذرت الاستعادة. حاول مرة أخرى.')));
  } on ApiNetworkException {
    messenger.showSnackBar(const SnackBar(
        content: Text('تعذر الاتصال بالسيرفر. تأكد من اتصالك وحاول مرة أخرى.')));
  } catch (_) {
    messenger.showSnackBar(const SnackBar(content: Text('تعذرت الاستعادة. حاول مرة أخرى.')));
  }
}
