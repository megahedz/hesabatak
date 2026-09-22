/// Maps 1:1 to GET /companies/{id}/dashboard.
class DashboardData {
  DashboardData({
    required this.cashBalance,
    required this.bankBalance,
    required this.receivableFromCustomers,
    required this.payableToSuppliers,
    required this.monthSales,
    required this.monthExpenses,
    required this.netProfit,
    required this.currencyLabel,
  });

  final double cashBalance;
  final double bankBalance;
  final double receivableFromCustomers;
  final double payableToSuppliers;
  final double monthSales;
  final double monthExpenses;
  final double netProfit;
  final String currencyLabel;

  factory DashboardData.fromJson(Map<String, dynamic> json) {
    double parse(String key) => double.parse(json[key] as String);
    return DashboardData(
      cashBalance: parse('رصيد_الخزينة'),
      bankBalance: parse('رصيد_البنك'),
      receivableFromCustomers: parse('لدى_العملاء'),
      payableToSuppliers: parse('للموردين'),
      monthSales: parse('مبيعات_الشهر'),
      monthExpenses: parse('المصروفات'),
      netProfit: parse('صافي_الربح'),
      currencyLabel: json['العملة'] as String,
    );
  }
}
