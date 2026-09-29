import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import '../../core/api_client.dart';
import '../../core/app_config.dart';
import '../../ui/theme.dart';
import '../../ui/widgets.dart';
import '../home/home_shell.dart';

/// الأصول الثابتة — رصيد حساب الأصول من دفتر الأستاذ + سجل حركاته، وإضافة
/// أصل جديد (سحبه من الخزينة أو البنك). حتى تصل عملية أصول مخصصة في السيرفر
/// نستخدم التحويل بين الحسابات: Assets Dr / Cash-Bank Cr — نفس القيد المحاسبي.
class FixedAssetsScreen extends StatefulWidget {
  const FixedAssetsScreen({super.key});

  @override
  State<FixedAssetsScreen> createState() => _FixedAssetsScreenState();
}

class _LedgerSummary {
  _LedgerSummary(this.closingBalance, this.lines);
  final double closingBalance;
  final List<Map<String, dynamic>> lines;
}

class _FixedAssetsScreenState extends State<FixedAssetsScreen> {
  final _api = ApiClient(baseUrl: AppConfig.apiBaseUrl);
  static const _assetCode = '1500';

  _LedgerSummary? _data;
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
      final gl = await _api.getGeneralLedger(AppConfig.companyId, _assetCode);
      if (!mounted) return;
      final lines = (gl['lines'] as List<dynamic>? ?? const []).cast<Map<String, dynamic>>();
      setState(() {
        _data = _LedgerSummary(
          double.tryParse(gl['closing_balance'] as String? ?? '0') ?? 0,
          lines,
        );
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

  Future<void> _addAsset() async {
    final name = TextEditingController();
    final amountController = TextEditingController();
    String from = '1100'; // الخزينة
    bool saving = false;
    const sources = {'1100': 'الخزينة', '1200': 'البنك'};

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
              const Text('إضافة أصل ثابت',
                  style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800, color: AppColors.navy)),
              const SizedBox(height: 6),
              const Text(
                'يُسجَّل الأصل كتحويل من الخزينة أو البنك إلى حساب الأصول الثابتة (قيد: أصول مدين / نقدية دائن).',
                style: TextStyle(fontSize: 11.5, color: AppColors.textSecondary),
              ),
              const SizedBox(height: 14),
              TextField(
                controller: name,
                autofocus: true,
                decoration: const InputDecoration(labelText: 'وصف الأصل (مثال: ثلاجة عرض)'),
              ),
              const SizedBox(height: 10),
              TextField(
                controller: amountController,
                keyboardType: const TextInputType.numberWithOptions(decimal: true),
                decoration: const InputDecoration(labelText: 'التكلفة', suffixText: 'ج.م'),
              ),
              const SizedBox(height: 10),
              SegmentedButton<String>(
                segments: const [
                  ButtonSegment(value: '1100', label: Text('من الخزينة')),
                  ButtonSegment(value: '1200', label: Text('من البنك')),
                ],
                selected: {from},
                onSelectionChanged: (s) => setSheetState(() => from = s.first),
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
                        setSheetState(() => saving = true);
                        try {
                          await _api.postTransfer(
                            companyId: AppConfig.companyId,
                            amount: amount,
                            fromCode: from,
                            toCode: _assetCode,
                          );
                          if (sheetCtx.mounted) Navigator.of(sheetCtx).pop(true);
                        } on ApiException {
                          if (sheetCtx.mounted) {
                            ScaffoldMessenger.of(context).showSnackBar(
                                const SnackBar(content: Text('تعذر تسجيل الأصل — تأكد أن الرصيد يكفي')));
                          }
                        } catch (_) {
                          if (sheetCtx.mounted) {
                            ScaffoldMessenger.of(context).showSnackBar(
                                const SnackBar(content: Text('تعذر تسجيل الأصل. حاول مرة أخرى.')));
                          }
                        } finally {
                          setSheetState(() => saving = false);
                        }
                      },
                child: saving
                    ? const SizedBox(height: 18, width: 18, child: CircularProgressIndicator(strokeWidth: 2))
                    : const Text('حفظ الأصل'),
              ),
            ],
          ),
        ),
      ),
    );
    if (ok == true) _load();
    name.dispose();
    amountController.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final fmt = NumberFormat('#,##0.##', 'en');
    final lines = _data?.lines ?? const <Map<String, dynamic>>[];

    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppHeader(title: 'الأصول الثابتة'),
      floatingActionButton: FloatingActionButton.extended(
        backgroundColor: AppColors.primary,
        foregroundColor: Colors.white,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
        onPressed: _addAsset,
        icon: const Icon(Icons.add),
        label: const Text('إضافة أصل'),
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _failed
              ? _ErrorState(onRetry: _load)
              : RefreshIndicator(
                  color: AppColors.primary,
                  onRefresh: () async => _load(),
                  child: ListView(
                    padding: const EdgeInsets.fromLTRB(16, 16, 16, 90),
                    children: [
                      SectionCard(
                        child: Row(
                          children: [
                            const IconTile(
                              icon: Icons.domain_rounded,
                              background: AppColors.greenTint,
                              color: AppColors.greenDark,
                              size: 48,
                            ),
                            const SizedBox(width: 12),
                            const Expanded(
                              child: Text('إجمالي الأصول الثابتة',
                                  style: TextStyle(fontSize: 14, color: AppColors.textSecondary)),
                            ),
                            Text(AppFmt.money(_data?.closingBalance ?? 0),
                                style: const TextStyle(
                                    fontSize: 18, fontWeight: FontWeight.w800, color: AppColors.navy)),
                          ],
                        ),
                      ),
                      const SizedBox(height: 14),
                      SectionCard(
                        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 12),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            const Padding(
                              padding: EdgeInsets.symmetric(horizontal: 6),
                              child: SectionHeader('سجل حركات الأصول'),
                            ),
                            if (lines.isEmpty)
                              const Padding(
                                padding: EdgeInsets.symmetric(vertical: 18),
                                child: Text('لا توجد أصول مسجلة بعد — اضغط «إضافة أصل» للبدء',
                                    textAlign: TextAlign.center,
                                    style: TextStyle(color: AppColors.textSecondary, fontSize: 13)),
                              )
                            else
                              for (final line in lines)
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

class _ErrorState extends StatelessWidget {
  const _ErrorState({required this.onRetry});
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Text('تعذر تحميل الأصول. تأكد من الاتصال وحاول مرة أخرى.',
              textAlign: TextAlign.center,
              style: TextStyle(color: AppColors.textSecondary)),
          const SizedBox(height: 12),
          FilledButton(onPressed: onRetry, child: const Text('إعادة المحاولة')),
        ],
      ),
    );
  }
}
