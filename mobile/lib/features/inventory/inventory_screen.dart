import 'package:flutter/material.dart';
import '../../core/api_client.dart';
import '../../core/app_config.dart';
import '../../ui/theme.dart';
import '../../ui/widgets.dart';
import '../home/home_shell.dart';

/// المخزون — الأصناف مع رصيدها الحالي وقيمتها بتكلفة المتوسط المرجح،
/// تنبيه الأصناف المنخفضة/النافدة، وإضافة صنف جديد (مع مخزون افتتاحي).
class InventoryScreen extends StatefulWidget {
  const InventoryScreen({super.key});

  @override
  State<InventoryScreen> createState() => _InventoryScreenState();
}

class _InventoryScreenState extends State<InventoryScreen> {
  final _api = ApiClient(baseUrl: AppConfig.apiBaseUrl);
  List<dynamic> _products = const [];
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
      final data = await _api.getProducts(AppConfig.companyId);
      if (!mounted) return;
      setState(() {
        _products = data;
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

  double _d(String? v) => double.tryParse(v ?? '') ?? 0;

  Future<void> _addProduct() async {
    final name = TextEditingController();
    final sku = TextEditingController();
    final unit = TextEditingController(text: 'قطعة');
    final purchase = TextEditingController();
    final selling = TextEditingController();
    final opening = TextEditingController();
    final minimum = TextEditingController();
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
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                const Text('إضافة صنف',
                    style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800, color: AppColors.navy)),
                const SizedBox(height: 14),
                TextField(
                  controller: name,
                  autofocus: true,
                  decoration: const InputDecoration(labelText: 'اسم الصنف *'),
                ),
                const SizedBox(height: 10),
                Row(
                  children: [
                    Expanded(
                      child: TextField(
                        controller: sku,
                        decoration: const InputDecoration(labelText: 'كود الصنف (اختياري)'),
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: TextField(
                        controller: unit,
                        decoration: const InputDecoration(labelText: 'الوحدة'),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 10),
                Row(
                  children: [
                    Expanded(
                      child: TextField(
                        controller: purchase,
                        keyboardType: const TextInputType.numberWithOptions(decimal: true),
                        decoration: const InputDecoration(labelText: 'سعر الشراء', suffixText: 'ج.م'),
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: TextField(
                        controller: selling,
                        keyboardType: const TextInputType.numberWithOptions(decimal: true),
                        decoration: const InputDecoration(labelText: 'سعر البيع', suffixText: 'ج.م'),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 10),
                Row(
                  children: [
                    Expanded(
                      child: TextField(
                        controller: opening,
                        keyboardType: const TextInputType.numberWithOptions(decimal: true),
                        decoration: const InputDecoration(labelText: 'كمية افتتاحية'),
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: TextField(
                        controller: minimum,
                        keyboardType: const TextInputType.numberWithOptions(decimal: true),
                        decoration: const InputDecoration(labelText: 'حد الطلب الأدنى'),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 6),
                const Text(
                  'لو أدخلت كمية افتتاحية سيُسجَّل مخزونها كمساهمة من رأس المال (تحتاج سعر شراء).',
                  style: TextStyle(fontSize: 11.5, color: AppColors.textSecondary),
                ),
                const SizedBox(height: 14),
                FilledButton(
                  onPressed: saving
                      ? null
                      : () async {
                          final n = name.text.trim();
                          if (n.isEmpty) {
                            ScaffoldMessenger.of(context)
                                .showSnackBar(const SnackBar(content: Text('اسم الصنف مطلوب')));
                            return;
                          }
                          setSheetState(() => saving = true);
                          try {
                            await _api.createProduct(
                              AppConfig.companyId,
                              name: n,
                              sku: sku.text.trim(),
                              unit: unit.text.trim().isEmpty ? 'قطعة' : unit.text.trim(),
                              purchasePrice: double.tryParse(purchase.text.trim()) ?? 0,
                              sellingPrice: double.tryParse(selling.text.trim()) ?? 0,
                              openingStockQty: double.tryParse(opening.text.trim()) ?? 0,
                              minimumStock: double.tryParse(minimum.text.trim()) ?? 0,
                            );
                            if (sheetCtx.mounted) Navigator.of(sheetCtx).pop(true);
                          } on ApiException catch (e) {
                            if (sheetCtx.mounted) {
                              ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                                  content: Text(e.statusCode == 400
                                      ? 'تحقق من البيانات — الكمية الافتتاحية تحتاج سعر شراء صحيح'
                                      : 'تعذر إضافة الصنف')));
                            }
                          } catch (_) {
                            if (sheetCtx.mounted) {
                              ScaffoldMessenger.of(context).showSnackBar(
                                  const SnackBar(content: Text('تعذر إضافة الصنف. حاول مرة أخرى.')));
                            }
                          } finally {
                            setSheetState(() => saving = false);
                          }
                        },
                  child: saving
                      ? const SizedBox(height: 18, width: 18, child: CircularProgressIndicator(strokeWidth: 2))
                      : const Text('حفظ الصنف'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
    if (ok == true) _load();
  }

  @override
  Widget build(BuildContext context) {
    final lowCount = _products.where((p) {
      final stock = _d(p['current_stock'] as String?);
      final min = _d(p['minimum_stock'] as String?);
      return min > 0 && stock <= min;
    }).length;

    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppHeader(title: 'المخزون'),
      floatingActionButton: FloatingActionButton.extended(
        backgroundColor: AppColors.primary,
        foregroundColor: Colors.white,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
        onPressed: _addProduct,
        icon: const Icon(Icons.add),
        label: const Text('إضافة صنف'),
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
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            Row(
                              children: [
                                const IconTile(
                                  icon: Icons.inventory_2_rounded,
                                  background: AppColors.amberTint,
                                  color: AppColors.amber,
                                  size: 44,
                                ),
                                const SizedBox(width: 10),
                                Expanded(
                                  child: Column(
                                    crossAxisAlignment: CrossAxisAlignment.start,
                                    children: [
                                      Text('${_products.length} صنف',
                                          style: const TextStyle(
                                              fontSize: 16, fontWeight: FontWeight.w800, color: AppColors.navy)),
                                      Text(
                                        lowCount > 0 ? '$lowCount صنف تحت حد الطلب' : 'كل الأصناف متوفرة',
                                        style: TextStyle(
                                            fontSize: 12,
                                            color: lowCount > 0 ? AppColors.red : AppColors.textSecondary),
                                      ),
                                    ],
                                  ),
                                ),
                              ],
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(height: 14),
                      if (_products.isEmpty)
                        SectionCard(
                          child: Padding(
                            padding: const EdgeInsets.symmetric(vertical: 24),
                            child: Column(
                              children: [
                                const Text('لا توجد أصناف بعد',
                                    style: TextStyle(color: AppColors.textSecondary)),
                                const SizedBox(height: 12),
                                FilledButton.icon(
                                  onPressed: _addProduct,
                                  icon: const Icon(Icons.add, size: 18),
                                  label: const Text('إضافة أول صنف'),
                                ),
                              ],
                            ),
                          ),
                        )
                      else
                        SectionCard(
                          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
                          child: Column(
                            children: [
                              for (final p in _products)
                                AppListTile(
                                  icon: Icons.inventory_2_rounded,
                                  title: p['name'] as String,
                                  subtitle: 'الرصيد: ${AppFmt.num(_d(p['current_stock'] as String?))} ${p['unit'] ?? ''}'
                                      ' — القيمة: ${AppFmt.money(_d(p['current_stock'] as String?) * _d(p['purchase_price'] as String?))}',
                                  trailingLabel: _statusLabel(p),
                                  trailingColor: _statusColor(p),
                                  trailingChevron: false,
                                ),
                            ],
                          ),
                        ),
                    ],
                  ),
                ),
    );
  }

  String? _statusLabel(Map<String, dynamic> p) {
    final stock = _d(p['current_stock'] as String?);
    final min = _d(p['minimum_stock'] as String?);
    if (min <= 0) return null;
    if (stock <= 0) return 'نفد';
    if (stock <= min) return 'منخفض';
    return null;
  }

  Color? _statusColor(Map<String, dynamic> p) {
    final stock = _d(p['current_stock'] as String?);
    final min = _d(p['minimum_stock'] as String?);
    if (min <= 0) return null;
    return stock <= 0 ? AppColors.red : AppColors.amber;
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
          const Text('تعذر تحميل المخزون. تأكد من الاتصال وحاول مرة أخرى.',
              textAlign: TextAlign.center,
              style: TextStyle(color: AppColors.textSecondary)),
          const SizedBox(height: 12),
          FilledButton(onPressed: onRetry, child: const Text('إعادة المحاولة')),
        ],
      ),
    );
  }
}
