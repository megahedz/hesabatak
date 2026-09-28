/// Maps 1:1 to GET /companies/{id}/dashboard.
class DashboardData {
  DashboardData({
    required this.cashBalance,
    required this.bankBalance,
    required this.receivableFromCustomers,
    required this.payableToSuppliers,
    required this.periodSales,
    required this.periodPurchases,
    required this.periodExpenses,
    required this.netProfit,
    required this.currencyLabel,
    required this.salesSeries,
  });

  final double cashBalance;
  final double bankBalance;
  final double receivableFromCustomers;
  final double payableToSuppliers;
  final double periodSales;
  final double periodPurchases;
  final double periodExpenses;
  final double netProfit;
  final String currencyLabel;

  /// [(تسمية الشهر، قيمة المبيعات)] آخر 6 أشهر، الأقدم أولًا.
  final List<(String, double)> salesSeries;

  factory DashboardData.fromJson(Map<String, dynamic> json) {
    double parse(String key) => double.parse(json[key] as String);
    final series = (json['مبيعات_آخر_6أشهر'] as List<dynamic>? ?? const [])
        .map((e) => (
              (e as Map<String, dynamic>)['label'] as String,
              double.parse(e['value'] as String),
            ))
        .toList();
    return DashboardData(
      cashBalance: parse('رصيد_الخزينة'),
      bankBalance: parse('رصيد_البنك'),
      receivableFromCustomers: parse('لدى_العملاء'),
      payableToSuppliers: parse('للموردين'),
      periodSales: parse('مبيعات_الفترة'),
      periodPurchases: parse('المشتريات'),
      periodExpenses: parse('المصروفات'),
      netProfit: parse('صافي_الربح'),
      currencyLabel: json['العملة'] as String,
      salesSeries: series,
    );
  }
}
