import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import '../../core/api_client.dart';
import '../../core/app_config.dart';
import 'export_service.dart';

/// التقارير (spec §38). Phase 3 scope: the three reports that read directly
/// off the accounting engine (already fully working server-side). The rest
/// (General Ledger, Cash Flow, Sales/Purchase/Expense reports, VAT report,
/// PDF/Excel export — spec §39/§40) come after Phase 4 (inventory/VAT).
class ReportsScreen extends StatefulWidget {
  const ReportsScreen({super.key});

  @override
  State<ReportsScreen> createState() => _ReportsScreenState();
}

class _ReportsScreenState extends State<ReportsScreen> with SingleTickerProviderStateMixin {
  final _api = ApiClient(baseUrl: AppConfig.apiBaseUrl);
  late TabController _tabController;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 6, vsync: this);
  }

  @override
  void dispose() {
    _tabController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('التقارير'),
        bottom: TabBar(
          controller: _tabController,
          isScrollable: true,
          tabAlignment: TabAlignment.start,
          tabs: const [
            Tab(text: 'المبيعات'),
            Tab(text: 'المشتريات'),
            Tab(text: 'المخزون'),
            Tab(text: 'ميزان المراجعة'),
            Tab(text: 'الميزانية'),
            Tab(text: 'الأرباح والخسائر'),
          ],
        ),
      ),
      body: TabBarView(
        controller: _tabController,
        children: [
          _SalesTab(api: _api),
          _PurchasesTab(api: _api),
          _InventoryTab(api: _api),
          _TrialBalanceTab(api: _api),
          _BalanceSheetTab(api: _api),
          _ProfitLossTab(api: _api),
        ],
      ),
    );
  }
}

// ======================================================================
// Phase 6: detailed reports (sales / purchases / inventory) + export
// ======================================================================
class _SalesTab extends StatelessWidget {
  const _SalesTab({required this.api});
  final ApiClient api;

  @override
  Widget build(BuildContext context) {
    return _DetailedReportList(
      api: api,
      futureFactory: api.getSalesReport,
      exportKey: 'sales',
      emptyText: 'لا توجد فواتير بيع بعد — سجّل أول عملية بيع من الرئيسية',
      rowBuilder: (context, r) {
        final total = double.parse(r['total'] as String);
        return ListTile(
          title: Text(r['customer_name'] as String? ?? 'عميل نقدي'),
          subtitle: Text('${r['invoice_number']} — ${r['invoice_date']}'
              '${(r['is_credit'] as bool) ? ' — آجل' : ''}'),
          trailing: Text('${fmtAr.format(total)} ج.م',
              style: const TextStyle(fontWeight: FontWeight.bold)),
        );
      },
    );
  }
}

class _PurchasesTab extends StatelessWidget {
  const _PurchasesTab({required this.api});
  final ApiClient api;

  @override
  Widget build(BuildContext context) {
    return _DetailedReportList(
      api: api,
      futureFactory: api.getPurchasesReport,
      exportKey: 'purchases',
      emptyText: 'لا توجد فواتير شراء بعد — سجّل أول عملية شراء من الرئيسية',
      rowBuilder: (context, r) {
        final total = double.parse(r['total'] as String);
        return ListTile(
          title: Text(r['supplier_name'] as String? ?? 'مورد نقدي'),
          subtitle: Text('${r['invoice_number']} — ${r['invoice_date']}'
              '${(r['is_credit'] as bool) ? ' — آجل' : ''}'),
          trailing: Text('${fmtAr.format(total)} ج.م',
              style: const TextStyle(fontWeight: FontWeight.bold)),
        );
      },
    );
  }
}

class _InventoryTab extends StatelessWidget {
  const _InventoryTab({required this.api});
  final ApiClient api;

  @override
  Widget build(BuildContext context) {
    return _DetailedReportList(
      api: api,
      futureFactory: api.getInventoryReport,
      exportKey: 'inventory',
      emptyText: 'لا توجد منتجات بعد',
      rowBuilder: (context, r) {
        final stock = double.parse(r['current_stock'] as String);
        final value = double.parse(r['stock_value'] as String);
        final isOut = r['is_out'] as bool;
        final isLow = r['is_low'] as bool;
        final sku = r['sku'] as String?;
        final title = sku == null || sku.isEmpty ? (r['name'] as String) : '${r['name']} ($sku)';
        final statusColor = isOut ? Colors.red : (isLow ? Colors.orange : Colors.green);
        final statusText = isOut ? 'نفد' : (isLow ? 'منخفض' : 'متوفر');
        return ListTile(
          title: Text(title),
          subtitle: Text('الرصيد: ${fmtAr.format(stock)} ${r['unit']} — القيمة: ${fmtAr.format(value)} ج.م'),
          trailing: Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
            decoration: BoxDecoration(
              color: statusColor.withOpacity(0.12),
              borderRadius: BorderRadius.circular(20),
            ),
            child: Text(statusText, style: TextStyle(color: statusColor, fontSize: 12, fontWeight: FontWeight.bold)),
          ),
        );
      },
    );
  }
}

final fmtAr = NumberFormat.decimalPattern('ar_EG');

class _DetailedReportList extends StatelessWidget {
  const _DetailedReportList({
    required this.api,
    required this.futureFactory,
    required this.exportKey,
    required this.emptyText,
    required this.rowBuilder,
  });

  final ApiClient api;
  final Future<Map<String, dynamic>> Function(int) futureFactory;
  final String exportKey;
  final String emptyText;
  final Widget Function(BuildContext, Map<String, dynamic>) rowBuilder;

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<Map<String, dynamic>>(
      future: futureFactory(AppConfig.companyId),
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const Center(child: CircularProgressIndicator());
        }
        if (snapshot.hasError) {
          return Center(child: Text('تعذر تحميل التقرير — تأكد من الاتصال وحاول مرة أخرى.'));
        }
        final data = snapshot.data!;
        final rows = (data['rows'] as List<dynamic>).cast<Map<String, dynamic>>();
        final totals = data['totals'] as Map<String, dynamic>;
        final totalLabel = totals['total'] != null ? 'الإجمالي' : 'قيمة المخزون';
        final totalValue = totals['total'] ?? totals['stock_value'];
        return Column(
          children: [
            Container(
              width: double.infinity,
              color: const Color(0xFF0F6E5C).withOpacity(0.08),
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text('$totalLabel: ${fmtAr.format(double.parse(totalValue as String))} ج.م',
                      style: const TextStyle(fontWeight: FontWeight.bold, color: Color(0xFF0F6E5C))),
                  TextButton.icon(
                    onPressed: () => shareReportExport(context, exportKey),
                    icon: const Icon(Icons.ios_share, size: 16),
                    label: const Text('تصدير'),
                  ),
                ],
              ),
            ),
            Expanded(
              child: rows.isEmpty
                  ? Center(child: Text(emptyText, textAlign: TextAlign.center))
                  : ListView.separated(
                      itemCount: rows.length,
                      separatorBuilder: (_, __) => const Divider(height: 1),
                      itemBuilder: (context, i) => rowBuilder(context, rows[i]),
                    ),
            ),
          ],
        );
      },
    );
  }
}

class _TrialBalanceTab extends StatelessWidget {
  const _TrialBalanceTab({required this.api});
  final ApiClient api;

  @override
  Widget build(BuildContext context) {
    final fmt = NumberFormat.decimalPattern('ar_EG');
    return FutureBuilder<Map<String, dynamic>>(
      future: api.getTrialBalance(AppConfig.companyId),
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const Center(child: CircularProgressIndicator());
        }
        if (snapshot.hasError) return const Center(child: Text('تعذر تحميل ميزان المراجعة.'));
        final data = snapshot.data!;
        final rows = data['rows'] as List<dynamic>;
        final isBalanced = data['is_balanced'] as bool;
        return Column(
          children: [
            Container(
              width: double.infinity,
              color: (isBalanced ? Colors.green : Colors.red).withOpacity(0.1),
              padding: const EdgeInsets.all(12),
              child: Text(
                isBalanced ? 'متوازن ✓  (مدين = دائن)' : 'غير متوازن — راجع القيود',
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontWeight: FontWeight.bold,
                  color: isBalanced ? Colors.green.shade800 : Colors.red.shade800,
                ),
              ),
            ),
            Expanded(
              child: ListView.separated(
                itemCount: rows.length,
                separatorBuilder: (_, __) => const Divider(height: 1),
                itemBuilder: (context, i) {
                  final r = rows[i] as Map<String, dynamic>;
                  final balance = double.parse(r['balance'] as String);
                  return ListTile(
                    title: Text(r['name_ar'] as String),
                    subtitle: Text(r['code'] as String),
                    trailing: Text('${fmt.format(balance)} ج.م', style: const TextStyle(fontWeight: FontWeight.bold)),
                  );
                },
              ),
            ),
          ],
        );
      },
    );
  }
}

class _BalanceSheetTab extends StatelessWidget {
  const _BalanceSheetTab({required this.api});
  final ApiClient api;

  @override
  Widget build(BuildContext context) {
    final fmt = NumberFormat.decimalPattern('ar_EG');
    return FutureBuilder<Map<String, dynamic>>(
      future: api.getBalanceSheet(AppConfig.companyId),
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const Center(child: CircularProgressIndicator());
        }
        if (snapshot.hasError) return const Center(child: Text('تعذر تحميل الميزانية.'));
        final d = snapshot.data!;
        String money(String key) => '${fmt.format(double.parse(d[key] as String))} ج.م';
        final isBalanced = d['is_balanced'] as bool;
        return ListView(
          padding: const EdgeInsets.all(16),
          children: [
            _ReportRow(label: 'الأصول (Assets)', value: money('assets'), emphasize: true),
            const Divider(),
            _ReportRow(label: 'الخصوم (Liabilities)', value: money('liabilities')),
            _ReportRow(label: 'حقوق الملكية (Equity)', value: money('equity')),
            _ReportRow(label: 'الخصوم + حقوق الملكية', value: money('liabilities_plus_equity'), emphasize: true),
            const SizedBox(height: 16),
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: (isBalanced ? Colors.green : Colors.red).withOpacity(0.1),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Text(
                isBalanced ? 'الأصول = الخصوم + حقوق الملكية ✓' : 'الميزانية غير متوازنة',
                textAlign: TextAlign.center,
                style: TextStyle(fontWeight: FontWeight.bold, color: isBalanced ? Colors.green.shade800 : Colors.red.shade800),
              ),
            ),
          ],
        );
      },
    );
  }
}

class _ProfitLossTab extends StatelessWidget {
  const _ProfitLossTab({required this.api});
  final ApiClient api;

  @override
  Widget build(BuildContext context) {
    final fmt = NumberFormat.decimalPattern('ar_EG');
    return FutureBuilder<Map<String, dynamic>>(
      future: api.getProfitAndLoss(AppConfig.companyId),
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const Center(child: CircularProgressIndicator());
        }
        if (snapshot.hasError) return const Center(child: Text('تعذر تحميل تقرير الأرباح والخسائر.'));
        final d = snapshot.data!;
        String money(String key) => '${fmt.format(double.parse(d[key] as String))} ج.م';
        final netProfit = double.parse(d['net_profit'] as String);
        return ListView(
          padding: const EdgeInsets.all(16),
          children: [
            _ReportRow(label: 'الإيرادات', value: money('revenue')),
            _ReportRow(label: 'تكلفة البضاعة المباعة', value: money('cogs')),
            const Divider(),
            _ReportRow(label: 'إجمالي الربح', value: money('gross_profit'), emphasize: true),
            _ReportRow(label: 'المصروفات التشغيلية', value: money('operating_expenses')),
            const Divider(),
            _ReportRow(
              label: netProfit >= 0 ? 'صافي الربح' : 'صافي الخسارة',
              value: money('net_profit'),
              emphasize: true,
              color: netProfit >= 0 ? Colors.green.shade700 : Colors.red.shade700,
            ),
          ],
        );
      },
    );
  }
}

class _ReportRow extends StatelessWidget {
  const _ReportRow({required this.label, required this.value, this.emphasize = false, this.color});
  final String label;
  final String value;
  final bool emphasize;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label, style: TextStyle(fontSize: emphasize ? 16 : 14, fontWeight: emphasize ? FontWeight.bold : FontWeight.normal)),
          Text(value, style: TextStyle(fontSize: emphasize ? 16 : 14, fontWeight: FontWeight.bold, color: color)),
        ],
      ),
    );
  }
}
