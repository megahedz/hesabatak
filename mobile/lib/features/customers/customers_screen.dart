import 'package:flutter/material.dart';
import 'package:characters/characters.dart';
import '../../core/api_client.dart';
import '../../core/app_config.dart';
import '../../ui/theme.dart';
import '../../ui/widgets.dart';
import '../home/home_shell.dart';
import '../../ui/attachment_field.dart';
import 'customer_model.dart';
import 'customer_statement_screen.dart';

/// العملاء — كالمرجع: زر «+ إضافة عميل» أزرق بعرض الشاشة، ثم حقل البحث،
/// ثم قائمة العملاء (أيقونة شخص زرقاء + الاسم + الهاتف + الرصيد + سهم).
class CustomersScreen extends StatefulWidget {
  const CustomersScreen({super.key});

  @override
  State<CustomersScreen> createState() => _CustomersScreenState();
}

class _CustomersScreenState extends State<CustomersScreen> {
  final _api = ApiClient(baseUrl: AppConfig.apiBaseUrl);
  late Future<List<CustomerSummary>> _future;
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
          .getCustomers(AppConfig.companyId)
          .then((list) => list.map((e) => CustomerSummary.fromJson(e as Map<String, dynamic>)).toList());
      _balances = _api.getCustomerBalances(AppConfig.companyId);
    });
  }

  Future<void> _openAddCustomerSheet() async {
    final created = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(20))),
      builder: (_) => const _AddCustomerSheet(),
    );
    if (created == true) _load();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppHeader(title: 'العملاء', actions: [
        IconButton(
          tooltip: 'بحث',
          icon: const Icon(Icons.search, color: AppColors.navy),
          onPressed: () {},
        ),
      ]),
      body: FutureBuilder<List<CustomerSummary>>(
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
                  const Text('تعذر تحميل قائمة العملاء.',
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
                      onPressed: _openAddCustomerSheet,
                      icon: const Icon(Icons.person_add_alt, size: 20),
                      label: const Text('إضافة عميل'),
                    ),
                    const SizedBox(height: 12),
                    TextField(
                      onChanged: (v) => setState(() => _query = v),
                      decoration: InputDecoration(
                        hintText: 'البحث عن عميل...',
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
                    final customers =
                        all.where((c) => _query.isEmpty || c.name.contains(_query)).toList();
                    if (customers.isEmpty) {
                      return const Center(
                        child: Padding(
                          padding: EdgeInsets.all(24),
                          child: Text(
                            'لا يوجد عملاء بعد. اضغط «إضافة عميل» لإضافة أول عميل.',
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
                        itemCount: customers.length,
                        separatorBuilder: (_, __) => const SizedBox(height: 10),
                        itemBuilder: (context, i) {
                          final c = customers[i];
                          final balance = balances[c.id] ?? 0.0;
                          return SectionCard(
                            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                            child: AppListTile(
                              icon: Icons.person_rounded,
                              title: c.name,
                              subtitle: c.phone != null && c.phone!.isNotEmpty ? c.phone! : '—',
                              trailingLabel: AppFmt.money(balance),
                              trailingColor: balance > 0 ? AppColors.red : AppColors.green,
                              onTap: () => Navigator.of(context).push(MaterialPageRoute(
                                  builder: (_) => CustomerStatementScreen(
                                      customerId: c.id, customerName: c.name))),
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

class _AddCustomerSheet extends StatefulWidget {
  const _AddCustomerSheet();

  @override
  State<_AddCustomerSheet> createState() => _AddCustomerSheetState();
}

class _AddCustomerSheetState extends State<_AddCustomerSheet> {
  final _api = ApiClient(baseUrl: AppConfig.apiBaseUrl);
  final _nameController = TextEditingController();
  final _phoneController = TextEditingController();
  final _openingBalanceController = TextEditingController(text: '0');
  bool _saving = false;

  int? _createdId;

  Future<void> _save() async {
    final name = _nameController.text.trim();
    if (name.isEmpty) {
      ScaffoldMessenger.of(context)
          .showSnackBar(const SnackBar(content: Text('من فضلك أدخل اسم العميل')));
      return;
    }
    setState(() => _saving = true);
    try {
      final res = await _api.createCustomer(
        companyId: AppConfig.companyId,
        name: name,
        phone: _phoneController.text.trim(),
        openingBalance: double.tryParse(_openingBalanceController.text.trim()) ?? 0,
      );
      _createdId = res['id'] as int?;
      // بعد الحفظ: تحويل النموذج لوضع «إرفاق ملفات» على العميل الجديد.
      if (mounted && _createdId != null) setState(() => _saved = true);
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('تعذر حفظ العميل. حاول مرة أخرى.')),
        );
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  bool _saved = false;

  @override
  Widget build(BuildContext context) {
    // وضع ما بعد الحفظ: إرفاق ملفات على العميل الجديد ثم إغلاق.
    if (_saved && _createdId != null) {
      return Padding(
        padding: EdgeInsets.only(
            left: 20, right: 20, top: 20, bottom: MediaQuery.of(context).viewInsets.bottom + 20),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text('تم حفظ العميل ✓',
                style: TextStyle(fontSize: 20, fontWeight: FontWeight.w800, color: AppColors.greenDark)),
            const SizedBox(height: 12),
            AttachmentField(ownerKind: 'customer', ownerId: _createdId!),
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
          const Text('عميل جديد',
              style: TextStyle(fontSize: 20, fontWeight: FontWeight.w800, color: AppColors.navy)),
          const SizedBox(height: 16),
          TextField(controller: _nameController, decoration: const InputDecoration(labelText: 'اسم العميل')),
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
              helperText: 'المبلغ الذي كان عليه قبل استخدام التطبيق',
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
