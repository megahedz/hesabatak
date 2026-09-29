import 'package:flutter/material.dart';
import '../../core/api_client.dart';
import '../../core/app_config.dart';
import '../../ui/theme.dart';
import '../../ui/widgets.dart';
import '../home/home_shell.dart';
import '../../ui/attachment_field.dart';
import 'supplier_model.dart';
import 'supplier_statement_screen.dart';

/// الموردون — نفس تصميم شاشة العملاء تمامًا (نظام موحد): زر إضافة أزرق،
/// بحث، ثم بطاقات (أيقونة + الاسم + الهاتف + الرصيد المستحق له).
class SuppliersScreen extends StatefulWidget {
  const SuppliersScreen({super.key});

  @override
  State<SuppliersScreen> createState() => _SuppliersScreenState();
}

class _SuppliersScreenState extends State<SuppliersScreen> {
  final _api = ApiClient(baseUrl: AppConfig.apiBaseUrl);
  late Future<List<SupplierSummary>> _future;
  late Future<Map<int, double>> _balances;
  String _query = '';

  @override
  void initState() {
    super.initState();
    _load();
  }

  void _load() {
    setState(() {
      _future = _api
          .getSuppliers(AppConfig.companyId)
          .then((list) => list.map((e) => SupplierSummary.fromJson(e as Map<String, dynamic>)).toList());
      _balances = _api.getSupplierBalances(AppConfig.companyId);
    });
  }

  Future<void> _openAddSupplierSheet() async {
    final created = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(20))),
      builder: (_) => const _AddSupplierSheet(),
    );
    if (created == true) _load();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppHeader(title: 'الموردون', actions: [
        IconButton(
          tooltip: 'بحث',
          icon: const Icon(Icons.search, color: AppColors.navy),
          onPressed: () {},
        ),
      ]),
      body: FutureBuilder<List<SupplierSummary>>(
        future: _future,
        builder: (context, snapshot) {
          if (snapshot.connectionState != ConnectionState.done) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snapshot.hasError) {
            return Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Text('تعذر تحميل قائمة الموردين.',
                      style: TextStyle(color: AppColors.textSecondary)),
                  const SizedBox(height: 8),
                  FilledButton(onPressed: _load, child: const Text('إعادة المحاولة')),
                ],
              ),
            );
          }
          final all = snapshot.data!;
          return Column(
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 10, 16, 0),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    FilledButton.icon(
                      onPressed: _openAddSupplierSheet,
                      icon: const Icon(Icons.add_business, size: 20),
                      label: const Text('إضافة مورد'),
                    ),
                    const SizedBox(height: 12),
                    TextField(
                      onChanged: (v) => setState(() => _query = v),
                      decoration: InputDecoration(
                        hintText: 'البحث عن مورد...',
                        prefixIcon: const Icon(Icons.search, color: AppColors.textSecondary),
                        contentPadding: const EdgeInsets.symmetric(vertical: 12),
                      ),
                    ),
                  ],
                ),
              ),
              Expanded(
                child: FutureBuilder<Map<int, double>>(
                  future: _balances,
                  builder: (context, balSnap) {
                    final balances = balSnap.data ?? const <int, double>{};
                    final suppliers =
                        all.where((s) => _query.isEmpty || s.name.contains(_query)).toList();
                    if (suppliers.isEmpty) {
                      return const Center(
                        child: Padding(
                          padding: EdgeInsets.all(24),
                          child: Text(
                            'لا يوجد موردون بعد. اضغط «إضافة مورد» لإضافة أول مورد.',
                            textAlign: TextAlign.center,
                            style: TextStyle(color: AppColors.textSecondary),
                          ),
                        ),
                      );
                    }
                    return RefreshIndicator(
                      onRefresh: () async => _load(),
                      color: AppColors.primary,
                      child: ListView.separated(
                        padding: const EdgeInsets.all(16),
                        itemCount: suppliers.length,
                        separatorBuilder: (_, __) => const SizedBox(height: 10),
                        itemBuilder: (context, i) {
                          final s = suppliers[i];
                          final balance = balances[s.id] ?? 0.0;
                          return SectionCard(
                            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                            child: AppListTile(
                              icon: Icons.storefront_rounded,
                              title: s.name,
                              subtitle: s.phone != null && s.phone!.isNotEmpty ? s.phone! : '—',
                              trailingLabel: AppFmt.money(balance),
                              trailingColor: balance > 0 ? AppColors.red : AppColors.green,
                              onTap: () => Navigator.of(context).push(MaterialPageRoute(
                                  builder: (_) => SupplierStatementScreen(
                                      supplierId: s.id, supplierName: s.name))),
                            ),
                          );
                        },
                      ),
                    );
                  },
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}

class _AddSupplierSheet extends StatefulWidget {
  const _AddSupplierSheet();

  @override
  State<_AddSupplierSheet> createState() => _AddSupplierSheetState();
}

class _AddSupplierSheetState extends State<_AddSupplierSheet> {
  final _api = ApiClient(baseUrl: AppConfig.apiBaseUrl);
  final _nameController = TextEditingController();
  final _phoneController = TextEditingController();
  final _openingBalanceController = TextEditingController(text: '0');
  bool _saving = false;

  int? _createdId;
  bool _saved = false;

  Future<void> _save() async {
    final name = _nameController.text.trim();
    if (name.isEmpty) {
      ScaffoldMessenger.of(context)
          .showSnackBar(const SnackBar(content: Text('من فضلك أدخل اسم المورد')));
      return;
    }
    setState(() => _saving = true);
    try {
      final res = await _api.createSupplier(
        companyId: AppConfig.companyId,
        name: name,
        phone: _phoneController.text.trim(),
        openingBalance: double.tryParse(_openingBalanceController.text.trim()) ?? 0,
      );
      _createdId = res['id'] as int?;
      // بعد الحفظ: تحويل النموذج لوضع «إرفاق ملفات» على المورد الجديد.
      if (mounted && _createdId != null) setState(() => _saved = true);
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('تعذر حفظ المورد. حاول مرة أخرى.')),
        );
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    // وضع ما بعد الحفظ: إرفاق ملفات على المورد الجديد ثم إغلاق.
    if (_saved && _createdId != null) {
      return Padding(
        padding: EdgeInsets.only(
            left: 20, right: 20, top: 20, bottom: MediaQuery.of(context).viewInsets.bottom + 20),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text('تم حفظ المورد ✓',
                style: TextStyle(fontSize: 20, fontWeight: FontWeight.w800, color: AppColors.greenDark)),
            const SizedBox(height: 12),
            AttachmentField(ownerKind: 'supplier', ownerId: _createdId!),
            const SizedBox(height: 12),
            FilledButton(
              onPressed: () => Navigator.of(context).pop(true),
              child: const Text('تم'),
            ),
          ],
        ),
      );
    }
    return Padding(
      padding: EdgeInsets.only(
          left: 20, right: 20, top: 20, bottom: MediaQuery.of(context).viewInsets.bottom + 20),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const Text('مورد جديد',
              style: TextStyle(fontSize: 20, fontWeight: FontWeight.w800, color: AppColors.navy)),
          const SizedBox(height: 16),
          TextField(controller: _nameController, decoration: const InputDecoration(labelText: 'اسم المورد')),
          const SizedBox(height: 12),
          TextField(
            controller: _phoneController,
            keyboardType: TextInputType.phone,
            decoration: const InputDecoration(labelText: 'رقم الهاتف (اختياري)'),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _openingBalanceController,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            decoration: const InputDecoration(
              labelText: 'رصيد افتتاحي (إن وُجد)',
              helperText: 'المبلغ الذي كان مستحقًا له قبل استخدام التطبيق',
              suffixText: 'ج.م',
            ),
          ),
          const SizedBox(height: 20),
          FilledButton(
            onPressed: _saving ? null : _save,
            child: _saving
                ? const SizedBox(height: 18, width: 18, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                : const Text('حفظ'),
          ),
        ],
      ),
    );
  }
}
