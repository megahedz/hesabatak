import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import '../../core/api_client.dart';
import '../../core/app_config.dart';
import '../../ui/theme.dart';
import '../../ui/widgets.dart';
import '../home/home_shell.dart';

/// الخزنة والبنك — رصيد كل حساب (من القيود) + سجل حركاته (دفتر الأستاذ)
/// + تحويل بين الخزينة والبنك، بتصميم النظام الموحد.
class TreasuryScreen extends StatefulWidget {
  const TreasuryScreen({super.key});

  @override
  State<TreasuryScreen> createState() => _TreasuryScreenState();
}

class _LedgerSummary {
  _LedgerSummary(this.closingBalance, this.lines);
  final double closingBalance;
  final List<Map<String, dynamic>> lines;
}

class _TreasuryScreenState extends State<TreasuryScreen> {
  final _api = ApiClient(baseUrl: AppConfig.apiBaseUrl);

  static const _cash = ('1100', 'الخزينة', Icons.savings_rounded, AppColors.purple, AppColors.purpleTint);
  static const _bank = ('1200', 'البنك', Icons.account_balance_rounded, AppColors.primary, AppColors.blueTint);

  _LedgerSummary? _cashData;
  _LedgerSummary? _bankData;
  bool _loading = true;
  bool _failed = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _failed = false;
    });
    try {
      final results = await Future.wait([
        _api.getGeneralLedger(AppConfig.companyId, _cash.$1),
        _api.getGeneralLedger(AppConfig.companyId, _bank.$1),
      ]);
      if (!mounted) return;
      setState(() {
        _cashData = _toSummary(results[0]);
        _bankData = _toSummary(results[1]);
        _loading = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _failed = true;
      });
    }
  }

  _LedgerSummary _toSummary(Map<String, dynamic> gl) {
    final lines = (gl['lines'] as List<dynamic>? ?? const [])
        .cast<Map<String, dynamic>>();
    return _LedgerSummary(
      double.tryParse(gl['closing_balance'] as String? ?? '0') ?? 0,
      lines,
    );
  }

  Future<void> _transfer() async {
    final amountController = TextEditingController();
    String from = _cash.$1; // الخزينة
    String to = _bank.$1; // البنك
    bool saving = false;
    final accounts = {_cash.$1: 'الخزينة', _bank.$1: 'البنك'};

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
              const Text('تحويل بين الحسابات',
                  style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800, color: AppColors.navy)),
              const SizedBox(height: 14),
              Row(
                children: [
                  Expanded(
                    child: DropdownButtonFormField<String>(
                      value: from,
                      decoration: const InputDecoration(labelText: 'من'),
                      items: accounts.entries
                          .map((e) => DropdownMenuItem(value: e.key, child: Text(e.value)))
                          .toList(),
                      onChanged: (v) => setSheetState(() => from = v!),
                    ),
                  ),
                  const Padding(
                    padding: EdgeInsets.symmetric(horizontal: 8),
                    child: Icon(Icons.swap_horiz_rounded, color: AppColors.primary),
                  ),
                  Expanded(
                    child: DropdownButtonFormField<String>(
                      value: to,
                      decoration: const InputDecoration(labelText: 'إلى'),
                      items: accounts.entries
                          .map((e) => DropdownMenuItem(value: e.key, child: Text(e.value)))
                          .toList(),
                      onChanged: (v) => setSheetState(() => to = v!),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              TextField(
                controller: amountController,
                autofocus: true,
                keyboardType: const TextInputType.numberWithOptions(decimal: true),
                decoration: const InputDecoration(labelText: 'المبلغ', suffixText: 'ج.م'),
              ),
              const SizedBox(height: 16),
              FilledButton(
                onPressed: saving
                    ? null
                    : () async {
                        final amount = double.tryParse(amountController.text.trim());
                        if (amount == null || amount <= 0) {
                          ScaffoldMessenger.of(context)
                              .showSnackBar(const SnackBar(content: Text('من فضلك أدخل مبلغًا صحيحًا')));
                          return;
                        }
                        if (from == to) {
                          ScaffoldMessenger.of(context)
                              .showSnackBar(const SnackBar(content: Text('اختر حسابين مختلفين')));
                          return;
                        }
                        setSheetState(() => saving = true);
                        try {
                          await _api.postTransfer(
                            companyId: AppConfig.companyId,
                            amount: amount,
                            fromCode: from,
                            toCode: to,
                          );
                          if (sheetCtx.mounted) Navigator.of(sheetCtx).pop(true);
                        } catch (_) {
                          if (sheetCtx.mounted) {
                            ScaffoldMessenger.of(context).showSnackBar(
                                const SnackBar(content: Text('تعذر تنفيذ التحويل. حاول مرة أخرى.')));
                          }
                        } finally {
                          setSheetState(() => saving = false);
                        }
                      },
                child: saving
                    ? const SizedBox(height: 18, width: 18, child: CircularProgressIndicator(strokeWidth: 2))
                    : const Text('تنفيذ التحويل'),
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
    final fmt = NumberFormat('#,##0.##', 'en');

    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppHeader(title: 'الخزنة والبنك'),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _failed
              ? _ErrorState(onRetry: _load)
              : RefreshIndicator(
                  color: AppColors.primary,
                  onRefresh: () async => _load(),
                  child: ListView(
                    padding: const EdgeInsets.all(16),
                    children: [
                      Row(
                        children: [
                          Expanded(child: _balanceCard(_cash, _cashData)),
                          const SizedBox(width: 10),
                          Expanded(child: _balanceCard(_bank, _bankData)),
                        ],
                      ),
                      const SizedBox(height: 14),
                      FilledButton.icon(
                        onPressed: _transfer,
                        icon: const Icon(Icons.swap_horiz_rounded, size: 20),
                        label: const Text('تحويل بين الخزينة والبنك'),
                      ),
                      const SizedBox(height: 14),
                      _ledgerCard(_cash, _cashData, fmt),
                      const SizedBox(height: 14),
                      _ledgerCard(_bank, _bankData, fmt),
                    ],
                  ),
                ),
    );
  }

  Widget _balanceCard(
      (String, String, IconData, Color, Color) account, _LedgerSummary? data) {
    final (_, label, icon, fg, bg) = account;
    return SectionCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          IconTile(icon: icon, background: bg, color: fg, size: 44),
          const SizedBox(height: 10),
          Text(label, style: const TextStyle(fontSize: 13, color: AppColors.textSecondary)),
          const SizedBox(height: 2),
          FittedBox(
            fit: BoxFit.scaleDown,
            child: Text(
              AppFmt.money(data?.closingBalance ?? 0),
              style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w800, color: AppColors.navy),
            ),
          ),
        ],
      ),
    );
  }

  Widget _ledgerCard(
      (String, String, IconData, Color, Color) account, _LedgerSummary? data, NumberFormat fmt) {
    final (_, label, _, _, _) = account;
    final lines = data?.lines ?? const <Map<String, dynamic>>[];
    return SectionCard(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 6),
            child: SectionHeader('حركات $label'),
          ),
          if (lines.isEmpty)
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 18),
              child: Text('لا توجد حركات بعد',
                  textAlign: TextAlign.center,
                  style: TextStyle(color: AppColors.textSecondary, fontSize: 13)),
            )
          else
            for (final line in lines.take(30))
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 4, horizontal: 6),
                child: Row(
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(line['description'] as String? ?? '',
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: const TextStyle(
                                  fontSize: 13, fontWeight: FontWeight.w600, color: AppColors.navy)),
                          Text(line['date'] as String? ?? '',
                              style: const TextStyle(
                                  fontSize: 11, color: AppColors.textSecondary)),
                        ],
                      ),
                    ),
                    const SizedBox(width: 8),
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.end,
                      children: [
                        Text(
                          (double.tryParse(line['debit'] as String? ?? '') ?? 0) > 0
                              ? '+${fmt.format(double.parse(line['debit'] as String))}'
                              : '-${fmt.format(double.tryParse(line['credit'] as String? ?? '') ?? 0)}',
                          style: TextStyle(
                            fontSize: 13.5,
                            fontWeight: FontWeight.w800,
                            color: (double.tryParse(line['debit'] as String? ?? '') ?? 0) > 0
                                ? AppColors.greenDark
                                : AppColors.red,
                          ),
                        ),
                        Text('رصيد ${fmt.format(double.tryParse(line['balance'] as String? ?? '') ?? 0)}',
                            style: const TextStyle(
                                fontSize: 11, color: AppColors.textSecondary)),
                      ],
                    ),
                  ],
                ),
              ),
        ],
      ),
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
          const Text('تعذر تحميل الأرصدة. تأكد من الاتصال وحاول مرة أخرى.',
              textAlign: TextAlign.center,
              style: TextStyle(color: AppColors.textSecondary)),
          const SizedBox(height: 12),
          FilledButton(onPressed: onRetry, child: const Text('إعادة المحاولة')),
        ],
      ),
    );
  }
}
