import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import '../../core/api_client.dart';
import '../../core/app_config.dart';
import '../../ui/theme.dart';
import '../../ui/widgets.dart';
import '../home/home_shell.dart';
import 'export_service.dart';

/// التقارير — التبويبات الستة (المبيعات/المشتريات/المخزون/ميزان المراجعة/
/// الميزانية/الأرباح والخسائر) بنفس منطق التقارير وبنظام التصميم الموحد.
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
      backgroundColor: AppColors.background,
      appBar: AppHeader(
        title: 'التقارير',
        actions: [
          IconButton(
            tooltip: 'تصدير PDF/Excel',
            icon: const Icon(Icons.ios_share, color: AppColors.navy, size: 20),
            onPressed: () => shareReportExport(context, 'sales'),
          ),
        ],
      ),
      body: Column(
        children: [
          Container(
            color: AppColors.background,
            child: TabBar(
              controller: _tabController,
              isScrollable: true,
              tabAlignment: TabAlignment.start,
              labelColor: AppColors.primary,
              unselectedLabelColor: AppColors.textSecondary,
              indicatorColor: AppColors.primary,
              dividerColor: AppColors.border,
              labelStyle: const TextStyle(fontWeight: FontWeight.w700, fontSize: 13.5),
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
          Expanded(
            child: TabBarView(
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
          ),
        ],
      ),
    );
  }
}

// ======================================================================
// التقارير التفصيلية (مبيعات / مشتريات / مخزون) + التصدير
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
        return _ReportTile(
          icon: Icons.receipt_long_rounded,
          title: r['customer_name'] as String? ?? 'عميل نقدي',
          subtitle: '${r['invoice_number']} — ${r['invoice_date']}'
              '${(r['is_credit'] as bool) ? ' — آجل' : ''}',
          value: '${AppFmt.num(total)} ج.م',
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
        return _ReportTile(
          icon: Icons.shopping_cart_rounded,
          title: r['supplier_name'] as String? ?? 'مورد نقدي',
          subtitle: '${r['invoice_number']} — ${r['invoice_date']}'
              '${(r['is_credit'] as bool) ? ' — آجل' : ''}',
          value: '${AppFmt.num(total)} ج.م',
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
        final statusColor = isOut ? AppColors.red : (isLow ? AppColors.amber : AppColors.green);
        final statusText = isOut ? 'نفد' : (isLow ? 'منخفض' : 'متوفر');
        return _ReportTile(
          icon: Icons.inventory_2_rounded,
          title: title,
          subtitle: 'الرصيد: ${AppFmt.num(stock)} ${r['unit']} — القيمة: ${AppFmt.money(value)}',
          value: statusText,
          valueColor: statusColor,
        );
      },
    );
  }
}

final fmtAr = NumberFormat('#,##0.##', 'en');

/// قائمة تقرير تفصيلي: شريط إجمالي + زر تصدير + صفوف البطاقات.
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
        return ListView(
          padding: const EdgeInsets.all(16),
          children: [
            SectionCard(
              child: Row(
                children: [
                  Expanded(
                    child: Text('$totalLabel: ${AppFmt.money(double.parse(totalValue as String))}',
                        style: const TextStyle(
                            fontSize: 15, fontWeight: FontWeight.w800, color: AppColors.navy)),
                  ),
                  OutlinedButton.icon(
                    onPressed: () => shareReportExport(context, exportKey),
                    icon: const Icon(Icons.ios_share, size: 16),
                    label: const Text('تصدير', style: TextStyle(fontSize: 13)),
                    style: OutlinedButton.styleFrom(
                      minimumSize: const Size(0, 40),
                      padding: const EdgeInsets.symmetric(horizontal: 14),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 14),
            if (rows.isEmpty)
              SectionCard(
                child: Padding(
                  padding: const EdgeInsets.symmetric(vertical: 24),
                  child: Text(emptyText, textAlign: TextAlign.center,
                      style: const TextStyle(color: AppColors.textSecondary)),
                ),
              )
            else
              SectionCard(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                child: Column(children: [for (final r in rows) rowBuilder(context, r)]),
              ),
          ],
        );
      },
    );
  }
}

/// صف تقرير قياسي داخل بطاقة.
class _ReportTile extends StatelessWidget {
  const _ReportTile({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.value,
    this.valueColor,
  });

  final IconData icon;
  final String title;
  final String subtitle;
  final String value;
  final Color? valueColor;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        children: [
          IconTile(icon: icon, background: AppColors.blueTint, color: AppColors.primary, size: 40),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                        fontSize: 14, fontWeight: FontWeight.w700, color: AppColors.navy)),
                const SizedBox(height: 2),
                Text(subtitle,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontSize: 12, color: AppColors.textSecondary)),
              ],
            ),
          ),
          const SizedBox(width: 8),
          Text(value,
              style: TextStyle(
                  fontSize: 13.5, fontWeight: FontWeight.w800, color: valueColor ?? AppColors.navy)),
        ],
      ),
    );
  }
}

// ======================================================================
// ميزان المراجعة / الميزانية / الأرباح والخسائر
// ======================================================================
class _TrialBalanceTab extends StatelessWidget {
  const _TrialBalanceTab({required this.api});
  final ApiClient api;

  @override
  Widget build(BuildContext context) {
    final fmt = NumberFormat('#,##0.##', 'en');
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
        return ListView(
          padding: const EdgeInsets.all(16),
          children: [
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: isBalanced ? AppColors.greenTint : AppColors.redTint,
                borderRadius: BorderRadius.circular(14),
              ),
              child: Text(
                isBalanced ? 'متوازن ✓  (مدين = دائن)' : 'غير متوازن — راجع القيود',
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontWeight: FontWeight.w800,
                  color: isBalanced ? AppColors.green : AppColors.red,
                ),
              ),
            ),
            const SizedBox(height: 14),
            SectionCard(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
              child: Column(
                children: [
                  for (final r in rows)
                    Padding(
                      padding: const EdgeInsets.symmetric(vertical: 4),
                      child: Row(
                        children: [
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(r['name_ar'] as String,
                                    style: const TextStyle(
                                        fontSize: 14, fontWeight: FontWeight.w600, color: AppColors.navy)),
                                Text(r['code'] as String,
                                    style: const TextStyle(
                                        fontSize: 11, color: AppColors.textSecondary)),
                              ],
                            ),
                          ),
                          Text('${fmt.format(double.parse(r['balance'] as String))} ج.م',
                              style: const TextStyle(
                                  fontSize: 13.5, fontWeight: FontWeight.w800, color: AppColors.navy)),
                        ],
                      ),
                    ),
                ],
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
    final fmt = NumberFormat('#,##0.##', 'en');
    return FutureBuilder<Map<String, dynamic>>(
      future: api.getBalanceSheet(AppConfig.companyId),
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const Center(child: CircularProgressIndicator());
        }
        if (snapshot.hasError) return const Center(child: Text('تعذر تحميل الميزانية.'));
        final d = snapshot.data!;
        String money(String key) => AppFmt.money(double.parse(d[key] as String));
        final isBalanced = d['is_balanced'] as bool;
        return ListView(
          padding: const EdgeInsets.all(16),
          children: [
            SectionCard(
              child: Column(
                children: [
                  SummaryRow(label: 'الأصول (Assets)', value: money('assets'), emphasized: true),
                  const Divider(height: 16),
                  SummaryRow(label: 'الخصوم (Liabilities)', value: money('liabilities')),
                  SummaryRow(label: 'حقوق الملكية (Equity)', value: money('equity')),
                  SummaryRow(
                      label: 'الخصوم + حقوق الملكية',
                      value: money('liabilities_plus_equity'),
                      emphasized: true),
                ],
              ),
            ),
            const SizedBox(height: 14),
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: isBalanced ? AppColors.greenTint : AppColors.redTint,
                borderRadius: BorderRadius.circular(14),
              ),
              child: Text(
                isBalanced ? 'الأصول = الخصوم + حقوق الملكية ✓' : 'الميزانية غير متوازنة',
                textAlign: TextAlign.center,
                style: TextStyle(
                    fontWeight: FontWeight.w800,
                    color: isBalanced ? AppColors.green : AppColors.red),
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
    return FutureBuilder<Map<String, dynamic>>(
      future: api.getProfitAndLoss(AppConfig.companyId),
      builder: (context, snapshot) {
        if (snapshot.connectionState != ConnectionState.done) {
          return const Center(child: CircularProgressIndicator());
        }
        if (snapshot.hasError) {
          return const Center(child: Text('تعذر تحميل تقرير الأرباح والخسائر.'));
        }
        final d = snapshot.data!;
        String money(String key) => AppFmt.money(double.parse(d[key] as String));
        final netProfit = double.parse(d['net_profit'] as String);
        return ListView(
          padding: const EdgeInsets.all(16),
          children: [
            SectionCard(
              child: Column(
                children: [
                  SummaryRow(label: 'الإيرادات', value: money('revenue')),
                  SummaryRow(label: 'تكلفة البضاعة المباعة', value: money('cogs')),
                  const Divider(height: 16),
                  SummaryRow(label: 'إجمالي الربح', value: money('gross_profit'), emphasized: true),
                  SummaryRow(label: 'المصروفات التشغيلية', value: money('operating_expenses')),
                  const Divider(height: 16),
                  SummaryRow(
                    label: netProfit >= 0 ? 'صافي الربح' : 'صافي الخسارة',
                    value: money('net_profit'),
                    emphasized: true,
                    valueColor: netProfit >= 0 ? AppColors.green : AppColors.red,
                  ),
                ],
              ),
            ),
          ],
        );
      },
    );
  }
}
