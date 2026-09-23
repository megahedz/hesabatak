import 'package:flutter/material.dart';
import '../../core/api_client.dart';
import '../../core/app_config.dart';
import '../customers/customer_model.dart';
import '../suppliers/supplier_model.dart';

/// Opens the right quick-entry form for a dashboard action. All eight
/// operations from the spec are wired to real backend calls now:
/// بيع، شراء، قبض من عميل، دفع لمورد، مصروف، إيداع رأس مال، سحب شخصي، تحويل.
void showQuickActionSheet(BuildContext context, {required String action, required VoidCallback onDone}) {
  showModalBottomSheet(
    context: context,
    isScrollControlled: true,
    shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(20))),
    builder: (_) => _buildFormFor(action, onDone),
  );
}

Widget _buildFormFor(String action, VoidCallback onDone) {
  switch (action) {
    case 'بيع':
      return _InvoiceForm(kind: _InvoiceKind.sale, title: 'بيع', onDone: onDone);
    case 'شراء':
      return _InvoiceForm(kind: _InvoiceKind.purchase, title: 'شراء', onDone: onDone);
    case 'قبض من عميل':
      return _PartyPaymentForm(kind: _PaymentKind.fromCustomer, title: 'قبض من عميل', onDone: onDone);
    case 'دفع لمورد':
      return _PartyPaymentForm(kind: _PaymentKind.toSupplier, title: 'دفع لمورد', onDone: onDone);
    case 'مصروف':
      return _SimpleAmountForm(kind: _SimpleKind.expense, title: 'مصروف', onDone: onDone);
    case 'إيداع رأس مال':
      return _SimpleAmountForm(kind: _SimpleKind.capital, title: 'إيداع رأس مال', onDone: onDone);
    case 'سحب شخصي':
      return _SimpleAmountForm(kind: _SimpleKind.withdrawal, title: 'سحب شخصي', onDone: onDone);
    case 'تحويل بين الحسابات':
      return _TransferForm(onDone: onDone);
    default:
      return const Padding(padding: EdgeInsets.all(24), child: Text('عملية غير معروفة'));
  }
}

// ============================================================ shared bits
Widget _sheetWrapper(BuildContext context, Widget child) => Padding(
      padding: EdgeInsets.only(
        left: 20, right: 20, top: 20,
        bottom: MediaQuery.of(context).viewInsets.bottom + 20,
      ),
      child: child,
    );

// ============================================================ بيع / شراء
enum _InvoiceKind { sale, purchase }

class _InvoiceForm extends StatefulWidget {
  const _InvoiceForm({required this.kind, required this.title, required this.onDone});
  final _InvoiceKind kind;
  final String title;
  final VoidCallback onDone;

  @override
  State<_InvoiceForm> createState() => _InvoiceFormState();
}

class _InvoiceFormState extends State<_InvoiceForm> {
  final _api = ApiClient(baseUrl: AppConfig.apiBaseUrl);
  final _amountController = TextEditingController();
  bool _isCredit = false;
  String _method = 'cash';
  int? _selectedPartyId;
  bool _goesToInventory = false;
  bool _saving = false;
  List<dynamic> _parties = [];
  bool _loadingParties = false;

  bool get _isSale => widget.kind == _InvoiceKind.sale;

  Future<void> _loadPartiesIfNeeded() async {
    if (!_isCredit || _parties.isNotEmpty) return;
    setState(() => _loadingParties = true);
    try {
      _parties = _isSale
          ? await _api.getCustomers(AppConfig.companyId)
          : await _api.getSuppliers(AppConfig.companyId);
    } catch (_) {
      _parties = [];
    } finally {
      if (mounted) setState(() => _loadingParties = false);
    }
  }

  Future<void> _save() async {
    final amount = double.tryParse(_amountController.text.trim());
    if (amount == null || amount <= 0) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('من فضلك أدخل مبلغًا صحيحًا')));
      return;
    }
    if (_isCredit && _selectedPartyId == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(_isSale ? 'اختر العميل للبيع الآجل' : 'اختر المورد للشراء الآجل')),
      );
      return;
    }
    setState(() => _saving = true);
    try {
      if (_isSale) {
        await _api.postSale(
          companyId: AppConfig.companyId, amount: amount, isCredit: _isCredit,
          method: _method, customerId: _isCredit ? _selectedPartyId : null,
        );
      } else {
        await _api.postPurchase(
          companyId: AppConfig.companyId, amount: amount, isCredit: _isCredit,
          method: _method, supplierId: _isCredit ? _selectedPartyId : null,
          goesToInventory: _goesToInventory,
        );
      }
      if (mounted) {
        Navigator.of(context).pop();
        widget.onDone();
      }
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('تعذر حفظ العملية. حاول مرة أخرى.')));
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return _sheetWrapper(
      context,
      Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(widget.title, style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
          const SizedBox(height: 16),
          TextField(
            controller: _amountController,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            autofocus: true,
            decoration: const InputDecoration(labelText: 'المبلغ', suffixText: 'ج.م', border: OutlineInputBorder()),
          ),
          const SizedBox(height: 16),
          SegmentedButton<bool>(
            segments: const [
              ButtonSegment(value: false, label: Text('نقدي')),
              ButtonSegment(value: true, label: Text('آجل')),
            ],
            selected: {_isCredit},
            onSelectionChanged: (s) {
              setState(() => _isCredit = s.first);
              _loadPartiesIfNeeded();
            },
          ),
          if (_isCredit) ...[
            const SizedBox(height: 12),
            if (_loadingParties)
              const Center(child: Padding(padding: EdgeInsets.all(8), child: CircularProgressIndicator()))
            else if (_parties.isEmpty)
              Text(_isSale ? 'لا يوجد عملاء بعد — أضف عميلًا أولًا من شاشة العملاء' : 'لا يوجد موردون بعد — أضف موردًا أولًا من شاشة الموردين',
                  style: const TextStyle(color: Colors.redAccent))
            else
              DropdownButtonFormField<int>(
                value: _selectedPartyId,
                decoration: InputDecoration(labelText: _isSale ? 'العميل' : 'المورد', border: const OutlineInputBorder()),
                items: _parties
                    .map((p) => DropdownMenuItem<int>(value: p['id'] as int, child: Text(p['name'] as String)))
                    .toList(),
                onChanged: (v) => setState(() => _selectedPartyId = v),
              ),
          ],
          if (!_isSale) ...[
            const SizedBox(height: 12),
            CheckboxListTile(
              value: _goesToInventory,
              onChanged: (v) => setState(() => _goesToInventory = v ?? false),
              title: const Text('بضاعة تُضاف للمخزون'),
              subtitle: const Text('اتركها فارغة إذا كان الشراء مصروفًا تشغيليًا وليس بضاعة للبيع'),
              controlAffinity: ListTileControlAffinity.leading,
              contentPadding: EdgeInsets.zero,
            ),
          ],
          const SizedBox(height: 12),
          SegmentedButton<String>(
            segments: const [
              ButtonSegment(value: 'cash', label: Text('خزينة')),
              ButtonSegment(value: 'bank', label: Text('بنك')),
            ],
            selected: {_method},
            onSelectionChanged: (s) => setState(() => _method = s.first),
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

// ============================================================ قبض / دفع
enum _PaymentKind { fromCustomer, toSupplier }

class _PartyPaymentForm extends StatefulWidget {
  const _PartyPaymentForm({required this.kind, required this.title, required this.onDone});
  final _PaymentKind kind;
  final String title;
  final VoidCallback onDone;

  @override
  State<_PartyPaymentForm> createState() => _PartyPaymentFormState();
}

class _PartyPaymentFormState extends State<_PartyPaymentForm> {
  final _api = ApiClient(baseUrl: AppConfig.apiBaseUrl);
  final _amountController = TextEditingController();
  String _method = 'cash';
  int? _selectedPartyId;
  bool _saving = false;
  List<dynamic> _parties = [];
  bool _loadingParties = true;

  bool get _isCustomer => widget.kind == _PaymentKind.fromCustomer;

  @override
  void initState() {
    super.initState();
    _loadParties();
  }

  Future<void> _loadParties() async {
    try {
      _parties = _isCustomer
          ? await _api.getCustomers(AppConfig.companyId)
          : await _api.getSuppliers(AppConfig.companyId);
    } catch (_) {
      _parties = [];
    } finally {
      if (mounted) setState(() => _loadingParties = false);
    }
  }

  Future<void> _save() async {
    final amount = double.tryParse(_amountController.text.trim());
    if (amount == null || amount <= 0) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('من فضلك أدخل مبلغًا صحيحًا')));
      return;
    }
    if (_selectedPartyId == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(_isCustomer ? 'اختر العميل' : 'اختر المورد')),
      );
      return;
    }
    setState(() => _saving = true);
    try {
      if (_isCustomer) {
        await _api.postCustomerPayment(
          companyId: AppConfig.companyId, amount: amount, customerId: _selectedPartyId!, method: _method,
        );
      } else {
        await _api.postSupplierPayment(
          companyId: AppConfig.companyId, amount: amount, supplierId: _selectedPartyId!, method: _method,
        );
      }
      if (mounted) {
        Navigator.of(context).pop();
        widget.onDone();
      }
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('تعذر حفظ العملية. حاول مرة أخرى.')));
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return _sheetWrapper(
      context,
      Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(widget.title, style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
          const SizedBox(height: 16),
          if (_loadingParties)
            const Center(child: Padding(padding: EdgeInsets.all(8), child: CircularProgressIndicator()))
          else if (_parties.isEmpty)
            Text(_isCustomer ? 'لا يوجد عملاء بعد — أضف عميلًا أولًا من شاشة العملاء' : 'لا يوجد موردون بعد — أضف موردًا أولًا من شاشة الموردين',
                style: const TextStyle(color: Colors.redAccent))
          else
            DropdownButtonFormField<int>(
              value: _selectedPartyId,
              decoration: InputDecoration(labelText: _isCustomer ? 'العميل' : 'المورد', border: const OutlineInputBorder()),
              items: _parties
                  .map((p) => DropdownMenuItem<int>(value: p['id'] as int, child: Text(p['name'] as String)))
                  .toList(),
              onChanged: (v) => setState(() => _selectedPartyId = v),
            ),
          const SizedBox(height: 12),
          TextField(
            controller: _amountController,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            decoration: const InputDecoration(labelText: 'المبلغ', suffixText: 'ج.م', border: OutlineInputBorder()),
          ),
          const SizedBox(height: 12),
          SegmentedButton<String>(
            segments: const [
              ButtonSegment(value: 'cash', label: Text('خزينة')),
              ButtonSegment(value: 'bank', label: Text('بنك')),
            ],
            selected: {_method},
            onSelectionChanged: (s) => setState(() => _method = s.first),
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

// ============================================================ مصروف / رأس مال / سحب
enum _SimpleKind { expense, capital, withdrawal }

class _SimpleAmountForm extends StatefulWidget {
  const _SimpleAmountForm({required this.kind, required this.title, required this.onDone});
  final _SimpleKind kind;
  final String title;
  final VoidCallback onDone;

  @override
  State<_SimpleAmountForm> createState() => _SimpleAmountFormState();
}

class _SimpleAmountFormState extends State<_SimpleAmountForm> {
  final _api = ApiClient(baseUrl: AppConfig.apiBaseUrl);
  final _amountController = TextEditingController();
  String _method = 'cash';
  bool _saving = false;

  Future<void> _save() async {
    final amount = double.tryParse(_amountController.text.trim());
    if (amount == null || amount <= 0) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('من فضلك أدخل مبلغًا صحيحًا')));
      return;
    }
    setState(() => _saving = true);
    try {
      switch (widget.kind) {
        case _SimpleKind.expense:
          await _api.postExpense(companyId: AppConfig.companyId, amount: amount, method: _method);
          break;
        case _SimpleKind.capital:
          await _api.postCapital(companyId: AppConfig.companyId, amount: amount, method: _method);
          break;
        case _SimpleKind.withdrawal:
          await _api.postOwnerWithdrawal(companyId: AppConfig.companyId, amount: amount, method: _method);
          break;
      }
      if (mounted) {
        Navigator.of(context).pop();
        widget.onDone();
      }
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('تعذر حفظ العملية. حاول مرة أخرى.')));
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return _sheetWrapper(
      context,
      Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(widget.title, style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
          const SizedBox(height: 16),
          TextField(
            controller: _amountController,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            autofocus: true,
            decoration: const InputDecoration(labelText: 'المبلغ', suffixText: 'ج.م', border: OutlineInputBorder()),
          ),
          const SizedBox(height: 12),
          SegmentedButton<String>(
            segments: const [
              ButtonSegment(value: 'cash', label: Text('خزينة')),
              ButtonSegment(value: 'bank', label: Text('بنك')),
            ],
            selected: {_method},
            onSelectionChanged: (s) => setState(() => _method = s.first),
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

// ============================================================ تحويل بين الحسابات
class _TransferForm extends StatefulWidget {
  const _TransferForm({required this.onDone});
  final VoidCallback onDone;

  @override
  State<_TransferForm> createState() => _TransferFormState();
}

class _TransferFormState extends State<_TransferForm> {
  final _api = ApiClient(baseUrl: AppConfig.apiBaseUrl);
  final _amountController = TextEditingController();
  String _fromCode = '1100'; // الخزينة
  String _toCode = '1200'; // البنك
  bool _saving = false;

  static const _accounts = {'1100': 'الخزينة', '1200': 'البنك'};

  Future<void> _save() async {
    final amount = double.tryParse(_amountController.text.trim());
    if (amount == null || amount <= 0) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('من فضلك أدخل مبلغًا صحيحًا')));
      return;
    }
    if (_fromCode == _toCode) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('اختر حسابين مختلفين')));
      return;
    }
    setState(() => _saving = true);
    try {
      await _api.postTransfer(companyId: AppConfig.companyId, amount: amount, fromCode: _fromCode, toCode: _toCode);
      if (mounted) {
        Navigator.of(context).pop();
        widget.onDone();
      }
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('تعذر حفظ العملية. حاول مرة أخرى.')));
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return _sheetWrapper(
      context,
      Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const Text('تحويل بين الحسابات', style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
          const SizedBox(height: 16),
          DropdownButtonFormField<String>(
            value: _fromCode,
            decoration: const InputDecoration(labelText: 'من', border: OutlineInputBorder()),
            items: _accounts.entries.map((e) => DropdownMenuItem(value: e.key, child: Text(e.value))).toList(),
            onChanged: (v) => setState(() => _fromCode = v!),
          ),
          const SizedBox(height: 12),
          DropdownButtonFormField<String>(
            value: _toCode,
            decoration: const InputDecoration(labelText: 'إلى', border: OutlineInputBorder()),
            items: _accounts.entries.map((e) => DropdownMenuItem(value: e.key, child: Text(e.value))).toList(),
            onChanged: (v) => setState(() => _toCode = v!),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _amountController,
            keyboardType: const TextInputType.numberWithOptions(decimal: true),
            decoration: const InputDecoration(labelText: 'المبلغ', suffixText: 'ج.م', border: OutlineInputBorder()),
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
