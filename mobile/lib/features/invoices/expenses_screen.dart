import 'package:flutter/material.dart';
import '../../core/api_client.dart';
import '../../core/app_config.dart';
import '../../ui/theme.dart';
import '../../ui/widgets.dart';
import '../home/home_shell.dart';

/// المصروفات — ملخص إجمالي المصروفات + إضافة مصروف، ثم تقرير المصروفات
/// مجمّع على حساباته (من القيود مباشرة) في بطاقات النظام الموحد.
class ExpensesScreen extends StatefulWidget {
  const ExpensesScreen({super.key});

  @override
  State<ExpensesScreen> createState() => _ExpensesScreenState();
}

/// حسابات المصروفات الجاهزة في دليل الحسابات (6900 = أخرى بدون تصنيف).
class _ExpenseAccount {
  const _ExpenseAccount(this.code, this.name, this.icon, this.bg, this.fg);
  final String code;
  final String name;
  final IconData icon;
  final Color bg;
  final Color fg;
}

class _ExpensesScreenState extends State<ExpensesScreen> {
  final _api = ApiClient(baseUrl: AppConfig.apiBaseUrl);

  static const _accounts = <_ExpenseAccount>[
    _ExpenseAccount('6100', 'إيجار', Icons.home_work_rounded, AppColors.purpleTint, AppColors.purple),
    _ExpenseAccount('6200', 'كهرباء ومياه', Icons.bolt_rounded, AppColors.amberTint, AppColors.amber),
    _ExpenseAccount('6300', 'مرتبات', Icons.badge_rounded, AppColors.blueTint, AppColors.primary),
    _ExpenseAccount('6400', 'مواصلات', Icons.local_shipping_rounded, AppColors.tealTint, AppColors.teal),
    _ExpenseAccount('6500', 'صيانة', Icons.build_rounded, AppColors.greyTint, AppColors.textSecondary),
    _ExpenseAccount('6600', 'تسويق', Icons.campaign_rounded, AppColors.greenTint, AppColors.green),
    _ExpenseAccount('6900', 'مصروفات أخرى', Icons.receipt_long_rounded, AppColors.redTint, AppColors.red),
  ];

  Map<String, dynamic>? _report;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final data = await _api.getExpensesReport(AppConfig.companyId);
      if (!mounted) return;
      setState(() => _report = data);
    } catch (_) {
      if (!mounted) return;
      setState(() => _report = {'rows': [], 'total': '0.00'});
    }
  }

  Future<void> _addExpense() async {
    final picked = await showModalBottomSheet<_ExpenseAccount>(
      context: context,
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(20))),
      builder: (ctx) => SafeArea(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Padding(
              padding: EdgeInsets.all(14),
              child: Text('اختر نوع المصروف',
                  style: TextStyle(fontSize: 16, fontWeight: FontWeight.w800, color: AppColors.navy)),
            ),
            for (final a in _accounts)
              ListTile(
                leading: IconTile(icon: a.icon, background: a.bg, color: a.fg, size: 40),
                title: Text(a.name),
                onTap: () => Navigator.of(ctx).pop(a),
              ),
          ],
        ),
      ),
    );
    if (picked == null || !mounted) return;

    // نفس نموذج الإدخال السريع الموجود — لكن بحساب مصروف محدد.
    final amountController = TextEditingController();
    String method = 'cash';
    bool saving = false;
    final ok = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(20))),
      builder: (sheetCtx) => StatefulBuilder(
        builder: (sheetCtx, setSheetState) => Padding(
          padding: EdgeInsets.only(
            left: 20, right: 20, top: 20,
            bottom: MediaQuery.of(sheetCtx).viewInsets.bottom + 20,
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text('مصروف: ${picked.name}',
                  style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w800, color: AppColors.navy)),
              const SizedBox(height: 14),
              TextField(
                controller: amountController,
                autofocus: true,
                keyboardType: const TextInputType.numberWithOptions(decimal: true),
                decoration: const InputDecoration(labelText: 'المبلغ', suffixText: 'ج.م'),
              ),
              const SizedBox(height: 12),
              Row(
                children: [
                  Expanded(
                    child: SegmentedButton<String>(
                      segments: const [
                        ButtonSegment(value: 'cash', label: Text('خزينة')),
                        ButtonSegment(value: 'bank', label: Text('بنك')),
                      ],
                      selected: {method},
                      onSelectionChanged: (s) => setSheetState(() => method = s.first),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 16),
              FilledButton(
                onPressed: saving
                    ? null
                    : () async {
                        final amount = double.tryParse(amountController.text.trim());
                        if (amount == null || amount <= 0) {
                          ScaffoldMessenger.of(context).showSnackBar(
                              const SnackBar(content: Text('من فضلك أدخل مبلغًا صحيحًا')));
                          return;
                        }
                        setSheetState(() => saving = true);
                        try {
                          await _api.postExpense(
                            companyId: AppConfig.companyId,
                            amount: amount,
                            method: method,
                            expenseAccountCode: picked.code,
                          );
                          if (sheetCtx.mounted) Navigator.of(sheetCtx).pop(true);
                        } catch (_) {
                          if (sheetCtx.mounted) {
                            ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
                                content: Text('تعذر حفظ المصروف. حاول مرة أخرى.')));
                          }
                        } finally {
                          setSheetState(() => saving = false);
                        }
                      },
                child: saving
                    ? const SizedBox(height: 18, width: 18, child: CircularProgressIndicator(strokeWidth: 2))
                    : const Text('حفظ المصروف'),
              ),
            ],
          ),
        ),
      ),
    );
    if (ok == true) _load();
  }

  @override
  Widget build(BuildContext context) {
    final rows = (_report?['rows'] as List<dynamic>?) ?? const [];
    final total = double.tryParse(_report?['total'] as String? ?? '0') ?? 0;
    // تجميع الأرقام على حسابات الشاشة (كل الحسابات تظهر حتى الصفرية).
    final byCode = <String, double>{
      for (final r in rows) r['code'] as String: double.tryParse(r['amount'] as String? ?? '0') ?? 0,
    };

    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppHeader(title: 'المصروفات'),
      floatingActionButton: FloatingActionButton.extended(
        backgroundColor: AppColors.primary,
        foregroundColor: Colors.white,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
        onPressed: _addExpense,
        icon: const Icon(Icons.add),
        label: const Text('مصروف جديد'),
      ),
      body: RefreshIndicator(
        color: AppColors.primary,
        onRefresh: () async => _load(),
        child: ListView(
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 90),
          children: [
            // ===== إجمالي المصروفات =====
            SectionCard(
              child: Row(
                children: [
                  const IconTile(
                    icon: Icons.account_balance_wallet_rounded,
                    background: AppColors.redTint,
                    color: AppColors.red,
                    size: 48,
                  ),
                  const SizedBox(width: 12),
                  const Expanded(
                    child: Text('إجمالي المصروفات',
                        style: TextStyle(fontSize: 14, color: AppColors.textSecondary)),
                  ),
                  Text(AppFmt.money(total),
                      style: const TextStyle(
                          fontSize: 20, fontWeight: FontWeight.w800, color: AppColors.navy)),
                ],
              ),
            ),
            const SizedBox(height: 14),

            // ===== المصروفات حسب النوع =====
            SectionCard(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const SectionHeader('المصروفات حسب النوع'),
                  if (rows.isEmpty)
                    const Padding(
                      padding: EdgeInsets.symmetric(vertical: 24),
                      child: Text('لا توجد مصروفات مسجلة بعد — اضغط «مصروف جديد» للبدء',
                          textAlign: TextAlign.center,
                          style: TextStyle(color: AppColors.textSecondary, fontSize: 13)),
                    )
                  else
                    for (final a in _accounts)
                      if ((byCode[a.code] ?? 0) > 0)
                        Padding(
                          padding: const EdgeInsets.symmetric(vertical: 6),
                          child: Row(
                            children: [
                              IconTile(icon: a.icon, background: a.bg, color: a.fg, size: 40),
                              const SizedBox(width: 10),
                              Expanded(
                                child: Text(a.name,
                                    style: const TextStyle(
                                        fontSize: 14, fontWeight: FontWeight.w600, color: AppColors.navy)),
                              ),
                              Text(AppFmt.money(byCode[a.code] ?? 0),
                                  style: const TextStyle(
                                      fontSize: 14, fontWeight: FontWeight.w800, color: AppColors.navy)),
                            ],
                          ),
                        ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
