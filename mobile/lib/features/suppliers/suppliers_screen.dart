import 'package:flutter/material.dart';
import 'package:characters/characters.dart';
import '../../core/api_client.dart';
import '../../core/app_config.dart';
import 'supplier_model.dart';
import 'supplier_statement_screen.dart';

class SuppliersScreen extends StatefulWidget {
  const SuppliersScreen({super.key});

  @override
  State<SuppliersScreen> createState() => _SuppliersScreenState();
}

class _SuppliersScreenState extends State<SuppliersScreen> {
  final _api = ApiClient(baseUrl: AppConfig.apiBaseUrl);
  late Future<List<SupplierSummary>> _future;
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
      appBar: AppBar(
        title: const Text('الموردون'),
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(56),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            child: TextField(
              onChanged: (v) => setState(() => _query = v),
              decoration: InputDecoration(
                hintText: 'بحث عن مورد...',
                prefixIcon: const Icon(Icons.search),
                filled: true,
                border: OutlineInputBorder(borderRadius: BorderRadius.circular(12), borderSide: BorderSide.none),
              ),
            ),
          ),
        ),
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _openAddSupplierSheet,
        icon: const Icon(Icons.local_shipping_outlined),
        label: const Text('مورد جديد'),
      ),
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
                  const Text('تعذر تحميل قائمة الموردين.'),
                  const SizedBox(height: 8),
                  FilledButton(onPressed: _load, child: const Text('إعادة المحاولة')),
                ],
              ),
            );
          }
          final suppliers = snapshot.data!.where((s) => _query.isEmpty || s.name.contains(_query)).toList();

          if (suppliers.isEmpty) {
            return const Center(
              child: Padding(
                padding: EdgeInsets.all(24),
                child: Text('لا يوجد موردون بعد. اضغط "مورد جديد" لإضافة أول مورد.', textAlign: TextAlign.center),
              ),
            );
          }
          return RefreshIndicator(
            onRefresh: () async => _load(),
            child: ListView.separated(
              itemCount: suppliers.length,
              separatorBuilder: (_, __) => const Divider(height: 1),
              itemBuilder: (context, i) {
                final s = suppliers[i];
                return ListTile(
                  leading: CircleAvatar(child: Text(s.name.characters.first)),
                  title: Text(s.name),
                  subtitle: s.phone != null ? Text(s.phone!) : null,
                  trailing: const Icon(Icons.chevron_left),
                  onTap: () => Navigator.of(context).push(
                    MaterialPageRoute(builder: (_) => SupplierStatementScreen(supplierId: s.id, supplierName: s.name)),
                  ),
                );
              },
            ),
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

  Future<void> _save() async {
    final name = _nameController.text.trim();
    if (name.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('من فضلك أدخل اسم المورد')));
      return;
    }
    setState(() => _saving = true);
    try {
      await _api.createSupplier(
        companyId: AppConfig.companyId,
        name: name,
        phone: _phoneController.text.trim(),
        openingBalance: double.tryParse(_openingBalanceController.text.trim()) ?? 0,
      );
      if (mounted) Navigator.of(context).pop(true);
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
    return Padding(
      padding: EdgeInsets.only(left: 20, right: 20, top: 20, bottom: MediaQuery.of(context).viewInsets.bottom + 20),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const Text('مورد جديد', style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
          const SizedBox(height: 16),
          TextField(controller: _nameController, decoration: const InputDecoration(labelText: 'اسم المورد', border: OutlineInputBorder())),
          const SizedBox(height: 12),
          TextField(
            controller: _phoneController,
            keyboardType: TextInputType.phone,
            decoration: const InputDecoration(labelText: 'رقم الهاتف (اختياري)', border: OutlineInputBorder()),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _openingBalanceController,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            decoration: const InputDecoration(
              labelText: 'رصيد افتتاحي (إن وُجد)',
              helperText: 'المبلغ الذي كان مستحقًا له قبل استخدام التطبيق',
              suffixText: 'ج.م',
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 20),
          FilledButton(
            onPressed: _saving ? null : _save,
            child: _saving
                ? const SizedBox(height: 18, width: 18, child: CircularProgressIndicator(strokeWidth: 2))
                : const Text('حفظ'),
          ),
        ],
      ),
    );
  }
}
