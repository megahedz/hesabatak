import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import '../../core/api_client.dart';
import '../../core/app_config.dart';

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
    _tabController = TabController(length: 3, vsync: this);
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
          tabs: const [
            Tab(text: 'ميزان المراجعة'),
            Tab(text: 'الميزانية'),
            Tab(text: 'الأرباح والخسائر'),
          ],
        ),
      ),
      body: TabBarView(
        controller: _tabController,
        children: [_TrialBalanceTab(api: _api), _BalanceSheetTab(api: _api), _ProfitLossTab(api: _api)],
      ),
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
