class CustomerSummary {
  CustomerSummary({required this.id, required this.name, this.phone});
  final int id;
  final String name;
  final String? phone;

  factory CustomerSummary.fromJson(Map<String, dynamic> json) => CustomerSummary(
        id: json['id'] as int,
        name: json['name'] as String,
        phone: json['phone'] as String?,
      );
}

class StatementLine {
  StatementLine({
    required this.date,
    required this.description,
    required this.debit,
    required this.credit,
    required this.runningBalance,
  });

  final String date;
  final String description;
  final double debit;
  final double credit;
  final double runningBalance;
}

class Statement {
  Statement({
    required this.partyName,
    required this.openingBalance,
    required this.closingBalance,
    required this.lines,
  });

  final String partyName;
  final double openingBalance;
  final double closingBalance;
  final List<StatementLine> lines;

  factory Statement.fromCustomerJson(Map<String, dynamic> json) => Statement(
        partyName: json['اسم_العميل'] as String,
        openingBalance: double.parse(json['الرصيد_الافتتاحي'] as String),
        closingBalance: double.parse(json['الرصيد_الختامي'] as String),
        lines: (json['الحركات'] as List<dynamic>)
            .map((l) => StatementLine(
                  date: l['التاريخ'] as String,
                  description: l['البيان'] as String,
                  debit: double.parse(l['مدين'] as String),
                  credit: double.parse(l['دائن'] as String),
                  runningBalance: double.parse(l['الرصيد'] as String),
                ))
            .toList(),
      );

  factory Statement.fromSupplierJson(Map<String, dynamic> json) => Statement(
        partyName: json['اسم_المورد'] as String,
        openingBalance: double.parse(json['الرصيد_الافتتاحي'] as String),
        closingBalance: double.parse(json['الرصيد_الختامي'] as String),
        lines: (json['الحركات'] as List<dynamic>)
            .map((l) => StatementLine(
                  date: l['التاريخ'] as String,
                  description: l['البيان'] as String,
                  debit: double.parse(l['مدين'] as String),
                  credit: double.parse(l['دائن'] as String),
                  runningBalance: double.parse(l['الرصيد'] as String),
                ))
            .toList(),
      );
}
