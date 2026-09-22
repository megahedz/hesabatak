class SupplierSummary {
  SupplierSummary({required this.id, required this.name, this.phone});
  final int id;
  final String name;
  final String? phone;

  factory SupplierSummary.fromJson(Map<String, dynamic> json) => SupplierSummary(
        id: json['id'] as int,
        name: json['name'] as String,
        phone: json['phone'] as String?,
      );
}
