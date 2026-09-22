import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import '../../core/api_client.dart';
import '../../core/app_config.dart';
import '../../core/session.dart';
import '../operations/quick_actions_sheet.dart';
import 'dashboard_model.dart';

/// The حساباتك home screen. Cards and wording match exactly what was
/// requested — no literal-translation phrasing, just how an Egyptian shop
/// or workshop owner would actually read their numbers.
class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  final _api = ApiClient(baseUrl: AppConfig.apiBaseUrl);
  late Future<DashboardData> _future;

  @override
  void initState() {
    super.initState();
    _future = _api.getDashboard(AppConfig.companyId).then(DashboardData.fromJson);
  }

  void _reload() {
    setState(() {
      _future = _api.getDashboard(AppConfig.companyId).then(DashboardData.fromJson);
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('حساباتك'),
        actions: [
          IconButton(
            tooltip: 'تسجيل الخروج',
            icon: const Icon(Icons.logout),
            onPressed: () => AppSession.instance.logout(),
          ),
        ],
      ),
      body: FutureBuilder<DashboardData>(
        future: _future,
        builder: (context, snapshot) {
          if (snapshot.connectionState != ConnectionState.done) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snapshot.hasError) {
            // Friendly Arabic message, not the raw exception (spec §49).
            return _ErrorState(onRetry: _reload);
          }
          final data = snapshot.data!;
          return RefreshIndicator(
            onRefresh: () async => _reload(),
            child: ListView(
              padding: const EdgeInsets.all(16),
              children: [
                _BalanceCardsGrid(data: data),
                const SizedBox(height: 24),
                const Text('عمليات سريعة', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
                const SizedBox(height: 12),
                _QuickActionsGrid(onDone: _reload),
              ],
            ),
          );
        },
      ),
    );
  }
}

class _BalanceCardsGrid extends StatelessWidget {
  const _BalanceCardsGrid({required this.data});
  final DashboardData data;

  @override
  Widget build(BuildContext context) {
    final fmt = NumberFormat.decimalPattern('ar_EG');
    String money(double v) => '${fmt.format(v)} ${data.currencyLabel}';

    final cards = [
      _CardSpec('رصيد الخزينة', money(data.cashBalance), Icons.payments_outlined, Colors.teal),
      _CardSpec('رصيد البنك', money(data.bankBalance), Icons.account_balance_outlined, Colors.indigo),
      _CardSpec('لدى العملاء', money(data.receivableFromCustomers), Icons.people_outline, Colors.orange),
      _CardSpec('للموردين', money(data.payableToSuppliers), Icons.local_shipping_outlined, Colors.deepOrange),
      _CardSpec('مبيعات الشهر', money(data.monthSales), Icons.trending_up, Colors.green),
      _CardSpec('المصروفات', money(data.monthExpenses), Icons.trending_down, Colors.redAccent),
      _CardSpec('صافي الربح', money(data.netProfit), Icons.savings_outlined,
          data.netProfit >= 0 ? Colors.green.shade700 : Colors.red.shade700),
    ];

    return GridView.count(
      crossAxisCount: 2,
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      crossAxisSpacing: 12,
      mainAxisSpacing: 12,
      childAspectRatio: 1.5,
      children: cards.map((c) => _BalanceCard(spec: c)).toList(),
    );
  }
}

class _CardSpec {
  _CardSpec(this.label, this.value, this.icon, this.color);
  final String label;
  final String value;
  final IconData icon;
  final Color color;
}

class _BalanceCard extends StatelessWidget {
  const _BalanceCard({required this.spec});
  final _CardSpec spec;

  @override
  Widget build(BuildContext context) {
    return Card(
      elevation: 0,
      color: spec.color.withOpacity(0.08),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Icon(spec.icon, color: spec.color),
            Text(spec.label, style: const TextStyle(fontSize: 13, color: Colors.black54)),
            Text(spec.value,
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: spec.color)),
          ],
        ),
      ),
    );
  }
}

class _QuickActionsGrid extends StatelessWidget {
  const _QuickActionsGrid({required this.onDone});
  final VoidCallback onDone;

  static const _actions = [
    ('بيع', Icons.point_of_sale),
    ('شراء', Icons.shopping_cart_outlined),
    ('قبض من عميل', Icons.arrow_downward),
    ('دفع لمورد', Icons.arrow_upward),
    ('مصروف', Icons.receipt_long_outlined),
    ('إيداع رأس مال', Icons.add_business_outlined),
    ('سحب شخصي', Icons.person_outline),
    ('تحويل بين الحسابات', Icons.swap_horiz),
  ];

  @override
  Widget build(BuildContext context) {
    return GridView.count(
      crossAxisCount: 4,
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      crossAxisSpacing: 8,
      mainAxisSpacing: 12,
      children: _actions.map((a) {
        final (label, icon) = a;
        return InkWell(
          borderRadius: BorderRadius.circular(12),
          onTap: () => showQuickActionSheet(context, action: label, onDone: onDone),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              CircleAvatar(radius: 22, child: Icon(icon)),
              const SizedBox(height: 6),
              Text(label, textAlign: TextAlign.center, style: const TextStyle(fontSize: 11)),
            ],
          ),
        );
      }).toList(),
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
          const Text('تعذر تحميل البيانات. تأكد من الاتصال وحاول مرة أخرى.'),
          const SizedBox(height: 12),
          FilledButton(onPressed: onRetry, child: const Text('إعادة المحاولة')),
        ],
      ),
    );
  }
}
