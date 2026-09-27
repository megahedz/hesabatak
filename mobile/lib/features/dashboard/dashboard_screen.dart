import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:file_picker/file_picker.dart';
import '../../core/api_client.dart';
import '../../core/app_config.dart';
import '../../core/session.dart';
import '../operations/quick_actions_sheet.dart';
import '../reports/export_service.dart';
import 'dashboard_model.dart';

/// The حساباتك home screen. Cards and wording match exactly what was
/// requested — no literal-translation phrasing, just how an Egyptian shop
/// or workshop owner would actually read their numbers.
class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  final _api = ApiClient(baseUrl: AppConfig.apiBaseUrl);
  late Future<DashboardData> _future;

  @override
  void initState() {
    super.initState();
    _future = _api.getDashboard(AppConfig.companyId).then(DashboardData.fromJson);
  }

  void _reload() {
    setState(() {
      _future = _api.getDashboard(AppConfig.companyId).then(DashboardData.fromJson);
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('حساباتك'),
        actions: [
          IconButton(
            tooltip: 'النسخ الاحتياطي والاستعادة',
            icon: const Icon(Icons.settings_backup_restore),
            onPressed: () => showBackupSheet(context),
          ),
          IconButton(
            tooltip: 'تسجيل الخروج',
            icon: const Icon(Icons.logout),
            onPressed: () => AppSession.instance.logout(),
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
            child: ListView(
              padding: const EdgeInsets.all(16),
              children: [
                _BalanceCardsGrid(data: data),
                const SizedBox(height: 24),
                const Text('عمليات سريعة', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
                const SizedBox(height: 12),
                _QuickActionsGrid(onDone: _reload),
              ],
            ),
          );
        },
      ),
    );
  }
}

class _BalanceCardsGrid extends StatelessWidget {
  const _BalanceCardsGrid({required this.data});
  final DashboardData data;

  @override
  Widget build(BuildContext context) {
    final fmt = NumberFormat.decimalPattern('ar_EG');
    String money(double v) => '${fmt.format(v)} ${data.currencyLabel}';

    final cards = [
      _CardSpec('رصيد الخزينة', money(data.cashBalance), Icons.payments_outlined, Colors.teal),
      _CardSpec('رصيد البنك', money(data.bankBalance), Icons.account_balance_outlined, Colors.indigo),
      _CardSpec('لدى العملاء', money(data.receivableFromCustomers), Icons.people_outline, Colors.orange),
      _CardSpec('للموردين', money(data.payableToSuppliers), Icons.local_shipping_outlined, Colors.deepOrange),
      _CardSpec('مبيعات الشهر', money(data.monthSales), Icons.trending_up, Colors.green),
      _CardSpec('المصروفات', money(data.monthExpenses), Icons.trending_down, Colors.redAccent),
      _CardSpec('صافي الربح', money(data.netProfit), Icons.savings_outlined,
          data.netProfit >= 0 ? Colors.green.shade700 : Colors.red.shade700),
    ];

    return GridView.count(
      crossAxisCount: 2,
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      crossAxisSpacing: 12,
      mainAxisSpacing: 12,
      childAspectRatio: 1.5,
      children: cards.map((c) => _BalanceCard(spec: c)).toList(),
    );
  }
}

class _CardSpec {
  _CardSpec(this.label, this.value, this.icon, this.color);
  final String label;
  final String value;
  final IconData icon;
  final Color color;
}

class _BalanceCard extends StatelessWidget {
  const _BalanceCard({required this.spec});
  final _CardSpec spec;

  @override
  Widget build(BuildContext context) {
    return Card(
      elevation: 0,
      color: spec.color.withOpacity(0.08),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Icon(spec.icon, color: spec.color),
            Text(spec.label, style: const TextStyle(fontSize: 13, color: Colors.black54)),
            Text(spec.value,
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: spec.color)),
          ],
        ),
      ),
    );
  }
}

class _QuickActionsGrid extends StatelessWidget {
  const _QuickActionsGrid({required this.onDone});
  final VoidCallback onDone;

  static const _actions = [
    ('بيع', Icons.point_of_sale),
    ('شراء', Icons.shopping_cart_outlined),
    ('قبض من عميل', Icons.arrow_downward),
    ('دفع لمورد', Icons.arrow_upward),
    ('مصروف', Icons.receipt_long_outlined),
    ('إيداع رأس مال', Icons.add_business_outlined),
    ('سحب شخصي', Icons.person_outline),
    ('تحويل بين الحسابات', Icons.swap_horiz),
  ];

  @override
  Widget build(BuildContext context) {
    return GridView.count(
      crossAxisCount: 4,
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      crossAxisSpacing: 8,
      mainAxisSpacing: 12,
      children: _actions.map((a) {
        final (label, icon) = a;
        return InkWell(
          borderRadius: BorderRadius.circular(12),
          onTap: () => showQuickActionSheet(context, action: label, onDone: onDone),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              CircleAvatar(radius: 22, child: Icon(icon)),
              const SizedBox(height: 6),
              Text(label, textAlign: TextAlign.center, style: const TextStyle(fontSize: 11)),
            ],
          ),
        );
      }).toList(),
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
          const Text('تعذر تحميل البيانات. تأكد من الاتصال وحاول مرة أخرى.'),
          const SizedBox(height: 12),
          FilledButton(onPressed: onRetry, child: const Text('إعادة المحاولة')),
        ],
      ),
    );
  }
}

// ======================================================================
// Phase 6: backup & restore (spec §59/§60)
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
                style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            const Text('خذ نسخة كاملة من بيانات مشروعك، أو استعد نسخة سابقة. الاستعادة تستبدل كل البيانات الحالية.',
                style: TextStyle(color: Colors.black54, fontSize: 13)),
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
  final confirmed = await showDialog<bool>(
    context: context,
    builder: (dialogContext) {
      final controller = TextEditingController();
      return AlertDialog(
        title: const Text('تأكيد الاستعادة'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('سيتم استبدال كل بيانات المشروع الحالية ببيانات النسخة الاحتياطية. لا يمكن التراجع عن هذه الخطوة.'),
            const SizedBox(height: 12),
            TextField(
              controller: controller,
              keyboardType: TextInputType.text,
              decoration: const InputDecoration(
                labelText: 'اكتب «استعادة» للتأكيد',
                border: OutlineInputBorder(),
              ),
            ),
          ],
        ),
        actions: [
          TextButton(onPressed: () => Navigator.of(dialogContext).pop(false), child: const Text('إلغاء')),
          FilledButton(
            onPressed: () => Navigator.of(dialogContext).pop(controller.text.trim() == 'استعادة'),
            child: const Text('استعادة'),
          ),
        ],
      );
    },
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
