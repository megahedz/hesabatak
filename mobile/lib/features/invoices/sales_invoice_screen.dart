import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import '../../core/api_client.dart';
import '../../core/app_config.dart';
import '../../ui/theme.dart';
import '../../ui/widgets.dart';
import '../home/home_shell.dart';
import '../reports/export_service.dart';

/// فاتورة مبيعات — نفس بنية المرجع: رقم الفاتورة والتاريخ، العميل،
/// نقدي/آجل، طريقة الدفع، جدول البنود (الصنف/الكمية/السعر/الإجمالي مع حذف)،
/// إجمالي فرعي + خصم + ضريبة + ضريبة الخصم = الإجمالي، المدفوع والمتبقي،
/// ثم أزرار حفظ/مشاركة/طباعة.
///
/// ضريبة الخصم وفق قانون 91 لسنة 2005 (اختيارية لكل فاتورة): 1% توريدات /
/// 3% خدمات / 5% استشارات — العميل يخصمها عند السداد، وبعد الحفظ يمكن
/// مشاركة «إشعار الخصم» PDF.
///
/// الخصم يظهر كسطر في الفاتورة (ورقمها في الإجماليات) ويُطرح من البنود قبل
/// حفظها — السيرفر يرفض أي فاتورة لا يساوي مجموع بنودها إجماليها.
class SalesInvoiceScreen extends StatefulWidget {
  const SalesInvoiceScreen({super.key});

  @override
  State<SalesInvoiceScreen> createState() => _SalesInvoiceScreenState();
}

class _InvoiceItem {
  int? productId; // null = بند خدمة/نص حر بدون صنف معرّف
  String name = '';
  String description = '';
  double quantity = 1;
  double unitPrice = 0;
  double discount = 0;
  final TextEditingController descController = TextEditingController();

  void dispose() => descController.dispose();

  /// السعر الفعلي بعد خصم الخصم من البند — هذا ما يُرسل للسيرفر لأنه
  /// يتحقق أن إجمالي البنود (كمية × سعر) يساوي إجمالي الفاتورة.
  double get effectivePrice {
    if (quantity <= 0) return unitPrice;
    final net = (quantity * unitPrice - discount).clamp(0, double.infinity);
    return double.parse((net / quantity).toStringAsFixed(2));
  }

  double get lineTotal {
    if (quantity <= 0) return 0;
    return double.parse((quantity * effectivePrice).toStringAsFixed(2));
  }
}

class _SalesInvoiceScreenState extends State<SalesInvoiceScreen> {
  final _api = ApiClient(baseUrl: AppConfig.apiBaseUrl);
  final _dateController = TextEditingController();
  DateTime _date = DateTime.now();
  String _invoiceNumber = '…';
  List<dynamic> _customers = const [];
  List<dynamic> _products = const [];
  int? _customerId;
  bool _isCredit = false;
  String _method = 'cash';
  double _vatRate = 0;
  final List<_InvoiceItem> _items = [_InvoiceItem()];
  double _paid = 0;
  bool _saving = false;
  // ضريبة الخصم (قانون 91/2005): null = مطفأة، وإلا 'supply'|'service'|'consult'
  String? _withholdingKind;
  bool _withholdingEnabled = false;
  static const _whLabels = {'supply': 'توريدات 1%', 'service': 'خدمات 3%', 'consult': 'استشارات 5%'};
  static const _whRates = {'supply': 1.0, 'service': 3.0, 'consult': 5.0};

  @override
  void initState() {
    super.initState();
    _dateController.text = DateFormat('yyyy/MM/dd').format(_date);
    _load();
  }

  @override
  void dispose() {
    _dateController.dispose();
    for (final i in _items) {
      i.dispose();
    }
    super.dispose();
  }

  Future<void> _load() async {
    try {
      final results = await Future.wait([
        _api.getCustomers(AppConfig.companyId),
        _api.getProducts(AppConfig.companyId),
        _api.getSettings(AppConfig.companyId),
      ]);
      if (!mounted) return;
      setState(() {
        _customers = results[0] as List<dynamic>;
        _products = results[1] as List<dynamic>;
        final settings = results[2] as Map<String, dynamic>;
        _vatRate = settings['vat_enabled'] == true
            ? double.parse(settings['vat_rate'] as String)
            : 0.0;
        _withholdingEnabled = settings['withholding_enabled'] == true;
        _invoiceNumber = 'تلقائي';
      });
    } catch (_) {
      if (!mounted) return;
      setState(() => _invoiceNumber = 'تلقائي');
    }
  }

  double get _subtotal {
    // مجموع البنود بالسعر الفعلي — نفس الحساب الذي يعيد السيرفر على البنود.
    return double.parse(_items.fold<double>(0, (s, i) => s + i.lineTotal).toStringAsFixed(2));
  }

  double get _vat => _subtotal * _vatRate / 100;
  double get _withholding =>
      _withholdingKind == null ? 0 : _subtotal * (_whRates[_withholdingKind] ?? 0) / 100;
  double get _total => _subtotal + _vat;
  double get _remaining => (_total - _paid).clamp(0, double.infinity);

  Future<void> _pickDate() async {
    final picked = await showDatePicker(
      context: context,
      initialDate: _date,
      firstDate: DateTime(2020),
      lastDate: DateTime(2100),
      builder: (context, child) => Theme(
        data: Theme.of(context).copyWith(colorScheme: ColorScheme.fromSeed(seedColor: AppColors.primary)),
        child: child!,
      ),
    );
    if (picked == null) return;
    setState(() {
      _date = picked;
      _dateController.text = DateFormat('yyyy/MM/dd').format(picked);
    });
  }

  Future<void> _save() async {
    final total = _total;
    if (total <= 0) {
      _toast('أضف بندًا واحدًا على الأقل بقيمة أكبر من صفر');
      return;
    }
    if (_isCredit && _customerId == null) {
      _toast('الفاتورة الآجلة تحتاج اختيار عميل');
      return;
    }
    // كل بند لازم يبقى له صنف معرّف أو وصف خدمة مكتوب يدويًا.
    for (final i in _items) {
      if (i.lineTotal > 0 && i.productId == null && i.description.trim().isEmpty) {
        _toast('اكتب وصف الخدمة في كل بند بدون صنف (أو اختر صنفًا من القائمة)');
        return;
      }
    }
    setState(() => _saving = true);
    try {
      final items = _items
          .where((i) => i.lineTotal > 0 && (i.productId != null || i.description.trim().isNotEmpty))
          .map((i) => {
                'product_id': i.productId,
                'quantity': i.quantity,
                'unit_price': i.effectivePrice,
                if (i.description.trim().isNotEmpty) 'description': i.description.trim(),
              })
          .toList();
      final res = await _api.postSale(
        companyId: AppConfig.companyId,
        amount: double.parse(_subtotal.toStringAsFixed(2)),
        isCredit: _isCredit,
        method: _method,
        customerId: _customerId,
        vatAmount: double.parse(_vat.toStringAsFixed(2)),
        items: items.isEmpty ? null : items,
        withholdingKind: _withholdingKind,
        withholdingRate: _withholdingKind == null ? null : _whRates[_withholdingKind!],
      );
      final num = res['invoice_number'];
      final invoiceId = res['invoice_id'] as int?;
      if (!mounted) return;
      Navigator.of(context).maybePop();
      _toast(num == null ? 'تم الحفظ وسيُرفع تلقائيًا عند عودة الاتصال' : 'تم حفظ الفاتورة رقم $num');
      // ضريبة الخصم مفعّلة → اعرض إشعار الخصم فورًا بعد الحفظ.
      if (invoiceId != null && _withholdingKind != null && _withholding > 0) {
        await _shareWithholdingNotice(invoiceId);
      }
    } on ApiException catch (e) {
      _toast(e.statusCode == 400 ? 'تحقق من بيانات الفاتورة — تأكد من البنود والإجمالي' : 'تعذر حفظ الفاتورة');
    } catch (_) {
      _toast('تعذر حفظ الفاتورة. تأكد من الاتصال وحاول مرة أخرى.');
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  void _toast(String msg) {
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));
  }

  /// تنزيل «إشعار خصم وفق قانون 91 لسنة 2005» ومشاركته (WhatsApp/طابعة…).
  Future<void> _shareWithholdingNotice(int invoiceId) async {
    final messenger = ScaffoldMessenger.of(context);
    try {
      final api = ApiClient(baseUrl: AppConfig.apiBaseUrl);
      final file = await api.downloadWithholdingNotice(invoiceId, docType: 'sale');
      final ok = await shareFile(context, file.bytes, file.fileName);
      if (!ok) {
        messenger.showSnackBar(const SnackBar(content: Text('تعذر مشاركة إشعار الخصم.')));
      }
    } on ApiException catch (e) {
      messenger.showSnackBar(SnackBar(
          content: Text(e.statusCode == 403
              ? 'إشعار الخصم متاح لصاحب الشركة/المحاسب فقط'
              : 'تعذر تجهيز إشعار الخصم.')));
    } catch (_) {
      messenger.showSnackBar(
          const SnackBar(content: Text('تعذر تجهيز إشعار الخصم. تأكد من الاتصال.')));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppHeader(title: 'فاتورة مبيعات'),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          // ===== رقم الفاتورة + التاريخ =====
          Row(
            children: [
              Expanded(
                child: _LabeledField(
                  label: 'رقم الفاتورة',
                  child: Container(
                    height: 48,
                    alignment: AlignmentDirectional.centerStart,
                    padding: const EdgeInsets.symmetric(horizontal: 14),
                    decoration: BoxDecoration(
                      color: AppColors.greyTint,
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(color: AppColors.border),
                    ),
                    child: Text(_invoiceNumber, style: const TextStyle(fontSize: 14, color: AppColors.textSecondary)),
                  ),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: _LabeledField(
                  label: 'التاريخ',
                  child: InkWell(
                    borderRadius: BorderRadius.circular(12),
                    onTap: _pickDate,
                    child: Container(
                      height: 48,
                      padding: const EdgeInsets.symmetric(horizontal: 12),
                      decoration: BoxDecoration(
                        color: Colors.white,
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(color: AppColors.border),
                      ),
                      child: Row(
                        children: [
                          const Icon(Icons.calendar_today_outlined, size: 18, color: AppColors.primary),
                          const SizedBox(width: 8),
                          Text(_dateController.text, style: const TextStyle(fontSize: 14)),
                        ],
                      ),
                    ),
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),

          // ===== العميل =====
          _LabeledField(
            label: 'العميل',
            child: DropdownButtonFormField<int>(
              value: _customerId,
              isDense: true,
              hint: const Text('اختر العميل', style: TextStyle(fontSize: 14)),
              decoration: const InputDecoration(prefixIcon: Icon(Icons.person_outline, size: 20)),
              items: _customers
                  .map((c) => DropdownMenuItem<int>(
                        value: c['id'] as int,
                        child: Text(c['name'] as String, style: const TextStyle(fontSize: 14)),
                      ))
                  .toList(),
              onChanged: (v) => setState(() => _customerId = v),
            ),
          ),
          const SizedBox(height: 14),

          // ===== نقدي / آجل + طريقة الدفع =====
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: _LabeledField(
                  label: 'نوع البيع',
                  child: Row(
                    children: [
                      Expanded(
                        child: _SegmentChip(
                          label: 'نقدي',
                          selected: !_isCredit,
                          onTap: () => setState(() => _isCredit = false),
                        ),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: _SegmentChip(
                          label: 'آجل',
                          selected: _isCredit,
                          onTap: () => setState(() => _isCredit = true),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: _LabeledField(
                  label: 'طريقة الدفع',
                  child: Row(
                    children: [
                      Expanded(
                        child: _SegmentChip(
                          label: 'نقدي',
                          selected: _method == 'cash',
                          onTap: () => setState(() => _method = 'cash'),
                        ),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: _SegmentChip(
                          label: 'بنك',
                          selected: _method == 'bank',
                          onTap: () => setState(() => _method = 'bank'),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),

          // ===== البنود =====
          SectionCard(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    const Text('البنود',
                        style: TextStyle(fontSize: 15, fontWeight: FontWeight.w800, color: AppColors.navy)),
                    FilledButton.icon(
                      onPressed: () => setState(() => _items.add(_InvoiceItem())),
                      icon: const Icon(Icons.add, size: 18),
                      label: const Text('إضافة صنف', style: TextStyle(fontSize: 12.5)),
                      style: FilledButton.styleFrom(
                        minimumSize: const Size(0, 38),
                        padding: const EdgeInsets.symmetric(horizontal: 12),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                // رأس الجدول
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
                  decoration: BoxDecoration(
                    color: AppColors.greyTint,
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: const Row(
                    children: [
                      SizedBox(width: 36, child: Text('', style: TextStyle(fontSize: 11))),
                      Expanded(flex: 4, child: Text('الصنف / الخدمة', style: _headerStyle)),
                      Expanded(flex: 2, child: Text('الكمية', style: _headerStyle, textAlign: TextAlign.center)),
                      Expanded(flex: 3, child: Text('السعر', style: _headerStyle, textAlign: TextAlign.center)),
                      Expanded(flex: 3, child: Text('الإجمالي', style: _headerStyle, textAlign: TextAlign.center)),
                    ],
                  ),
                ),
                const SizedBox(height: 8),
                for (var i = 0; i < _items.length; i++) _itemRow(_items[i], i),
                const SizedBox(height: 4),
                Text(
                  'اختر صنفًا من القائمة، أو اتركه فارغًا واكتب وصف الخدمة يدويًا — وكل بند يقبل وصفًا يظهر في الفاتورة.',
                  style: TextStyle(fontSize: 11.5, color: AppColors.textSecondary),
                ),
              ],
            ),
          ),
          const SizedBox(height: 14),

          // ===== الإجماليات =====
          SectionCard(
            child: Column(
              children: [
                SummaryRow(label: 'الإجمالي الفرعي', value: AppFmt.money(_subtotal)),
                SummaryRow(label: 'خصم البنود', value: AppFmt.money(_items.fold<double>(0, (s, i) => s + i.discount))),
                SummaryRow(label: 'ضريبة القيمة المضافة (${AppFmt.num(_vatRate)}%)', value: AppFmt.money(_vat)),
                if (_withholdingEnabled)
                  Padding(
                    padding: const EdgeInsets.only(top: 4),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Row(
                          children: [
                            const Icon(Icons.account_balance_outlined, size: 18, color: AppColors.primary),
                            const SizedBox(width: 8),
                            const Text('ضريبة الخصم (قانون 91 لسنة 2005)',
                                style: TextStyle(fontSize: 13, fontWeight: FontWeight.w700, color: AppColors.navy)),
                            const Spacer(),
                            DropdownButton<String>(
                              value: _withholdingKind,
                              hint: const Text('مطفأة', style: TextStyle(fontSize: 12.5)),
                              underline: const SizedBox.shrink(),
                              items: const [
                                DropdownMenuItem(value: 'supply', child: Text('توريدات 1%', style: TextStyle(fontSize: 12.5))),
                                DropdownMenuItem(value: 'service', child: Text('خدمات 3%', style: TextStyle(fontSize: 12.5))),
                                DropdownMenuItem(value: 'consult', child: Text('استشارات 5%', style: TextStyle(fontSize: 12.5))),
                              ],
                              onChanged: (v) => setState(() => _withholdingKind = v),
                            ),
                          ],
                        ),
                        if (_withholdingKind != null)
                          SummaryRow(
                            label: 'خصم من العميل (${_whLabels[_withholdingKind]})',
                            value: '- ${AppFmt.money(_withholding)}',
                          ),
                      ],
                    ),
                  ),
                const Divider(height: 16),
                SummaryRow(label: 'الإجمالي الكلي', value: AppFmt.money(_total), emphasized: true),
                const SizedBox(height: 10),
                Row(
                  children: [
                    Expanded(
                      child: _LabeledField(
                        label: 'المدفوع',
                        child: TextField(
                          keyboardType: const TextInputType.numberWithOptions(decimal: true),
                          onChanged: (v) => setState(() => _paid = double.tryParse(v) ?? 0),
                          decoration: const InputDecoration(suffixText: 'ج.م', isDense: true),
                        ),
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: _LabeledField(
                        label: 'المتبقي',
                        child: Container(
                          height: 48,
                          alignment: AlignmentDirectional.centerStart,
                          padding: const EdgeInsets.symmetric(horizontal: 14),
                          decoration: BoxDecoration(
                            color: _remaining > 0 ? AppColors.greenTint : AppColors.greyTint,
                            borderRadius: BorderRadius.circular(12),
                            border: Border.all(color: AppColors.border),
                          ),
                          child: Text(
                            AppFmt.money(_remaining),
                            style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w700, color: AppColors.navy),
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),

          // ===== أزرار الحفظ/المشاركة/الطباعة =====
          Row(
            children: [
              Expanded(
                child: OutlinedButton.icon(
                  onPressed: () => _toast('جارٍ تجهيز مشاركة الفاتورة…'),
                  icon: const Icon(Icons.share_outlined, size: 18),
                  label: const Text('مشاركة', style: TextStyle(fontSize: 13.5)),
                  style: OutlinedButton.styleFrom(minimumSize: const Size.fromHeight(48)),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: OutlinedButton.icon(
                  onPressed: () => _toast('الطباعة متاحة بعد حفظ الفاتورة من التقارير'),
                  icon: const Icon(Icons.print_outlined, size: 18),
                  label: const Text('طباعة', style: TextStyle(fontSize: 13.5)),
                  style: OutlinedButton.styleFrom(minimumSize: const Size.fromHeight(48)),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                flex: 2,
                child: FilledButton.icon(
                  onPressed: _saving ? null : _save,
                  icon: _saving
                      ? const SizedBox(height: 16, width: 16, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                      : const Icon(Icons.save_outlined, size: 18),
                  label: const Text('حفظ', style: TextStyle(fontSize: 14)),
                  style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(48)),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _itemRow(_InvoiceItem item, int index) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              // حذف الصف (يمين الصف في RTL كالمرجع)
              SizedBox(
                width: 36,
                child: IconButton(
                  visualDensity: VisualDensity.compact,
                  padding: EdgeInsets.zero,
                  icon: const Icon(Icons.delete_outline, color: AppColors.red, size: 20),
                  onPressed: _items.length > 1
                      ? () => setState(() {
                            _items.removeAt(index).dispose();
                          })
                      : null,
                ),
              ),
              Expanded(
                flex: 4,
                child: DropdownButtonFormField<int>(
                  value: item.productId,
                  isDense: true,
                  hint: const Text('اختر صنفًا…', style: TextStyle(fontSize: 12.5)),
                  decoration: const InputDecoration(
                      contentPadding: EdgeInsets.symmetric(horizontal: 10, vertical: 8)),
                  items: _products
                      .map((p) => DropdownMenuItem<int>(
                            value: p['id'] as int,
                            child: Text(p['name'] as String,
                                style: const TextStyle(fontSize: 12.5),
                                overflow: TextOverflow.ellipsis),
                          ))
                      .toList(),
                  onChanged: (v) {
                    setState(() {
                      item.productId = v;
                      final p = _products.firstWhere(
                        (p) => p['id'] == v,
                        orElse: () => null,
                      );
                      if (p != null) {
                        item.name = p['name'] as String;
                        item.unitPrice = double.parse(p['selling_price'] as String);
                      }
                    });
                  },
                ),
              ),
              const SizedBox(width: 6),
              Expanded(
                flex: 2,
                child: _numField(item.quantity, (v) => item.quantity = v),
              ),
              const SizedBox(width: 6),
              Expanded(
                flex: 3,
                child: _numField(item.unitPrice, (v) => item.unitPrice = v),
              ),
              const SizedBox(width: 6),
              Expanded(
                flex: 3,
                child: Text(
                  AppFmt.num(item.lineTotal),
                  textAlign: TextAlign.center,
                  style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w700, color: AppColors.navy),
                ),
              ),
            ],
          ),
          // وصف البند — إجباري للبنود بدون صنف معرّف (خدمة)، اختياري لغيرها.
          Padding(
            padding: const EdgeInsets.only(top: 6, right: 36),
            child: TextField(
              controller: item.descController,
              style: const TextStyle(fontSize: 12.5),
              decoration: InputDecoration(
                isDense: true,
                hintText: item.productId == null
                    ? 'وصف الخدمة (إجباري) — مثال: إعداد عقد إيجار'
                    : 'وصف إضافي (اختياري)',
                hintStyle: TextStyle(
                    fontSize: 11.5,
                    color: item.productId == null ? AppColors.amber : AppColors.textSecondary),
                contentPadding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                border: OutlineInputBorder(borderRadius: BorderRadius.circular(10)),
              ),
              onChanged: (v) => item.description = v,
            ),
          ),
        ],
      ),
    );
  }

  Widget _numField(double initial, ValueChanged<double> onChanged) {
    return TextFormField(
      initialValue: initial == 0 ? '' : AppFmt.num(initial),
      keyboardType: const TextInputType.numberWithOptions(decimal: true),
      textAlign: TextAlign.center,
      style: const TextStyle(fontSize: 13),
      decoration: const InputDecoration(contentPadding: EdgeInsets.symmetric(horizontal: 8, vertical: 8)),
      onChanged: (v) {
        setState(() => onChanged(double.tryParse(v) ?? 0));
      },
    );
  }
}

const _headerStyle = TextStyle(fontSize: 11.5, fontWeight: FontWeight.w700, color: AppColors.textSecondary);

class _LabeledField extends StatelessWidget {
  const _LabeledField({required this.label, required this.child});
  final String label;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: const TextStyle(fontSize: 12, color: AppColors.textSecondary)),
        const SizedBox(height: 6),
        child,
      ],
    );
  }
}

class _SegmentChip extends StatelessWidget {
  const _SegmentChip({required this.label, required this.selected, required this.onTap});
  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      borderRadius: BorderRadius.circular(10),
      onTap: onTap,
      child: Container(
        height: 40,
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: selected ? AppColors.primary : Colors.white,
          borderRadius: BorderRadius.circular(10),
          border: Border.all(color: selected ? AppColors.primary : AppColors.border),
        ),
        child: Text(
          label,
          style: TextStyle(
            fontSize: 13.5,
            fontWeight: FontWeight.w700,
            color: selected ? Colors.white : AppColors.textSecondary,
          ),
        ),
      ),
    );
  }
}
