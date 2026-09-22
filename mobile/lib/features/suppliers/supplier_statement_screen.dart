import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import '../../core/api_client.dart';
import '../../core/app_config.dart';
import '../customers/customer_model.dart'; // shares the Statement/StatementLine model

/// كشف حساب المورد (spec §24).
class SupplierStatementScreen extends StatefulWidget {
  const SupplierStatementScreen({super.key, required this.supplierId, required this.supplierName});
  final int supplierId;
  final String supplierName;

  @override
  State<SupplierStatementScreen> createState() => _SupplierStatementScreenState();
}

class _SupplierStatementScreenState extends State<SupplierStatementScreen> {
  final _api = ApiClient(baseUrl: AppConfig.apiBaseUrl);
  late Future<Statement> _future;

  @override
  void initState() {
    super.initState();
    _future = _api
        .getSupplierStatement(AppConfig.companyId, widget.supplierId)
        .then((json) => Statement.fromSupplierJson(json));
  }

  @override
  Widget build(BuildContext context) {
    final fmt = NumberFormat.decimalPattern('ar_EG');
    return Scaffold(
      appBar: AppBar(title: Text('كشف حساب: ${widget.supplierName}')),
      body: FutureBuilder<Statement>(
        future: _future,
        builder: (context, snapshot) {
          if (snapshot.connectionState != ConnectionState.done) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snapshot.hasError) {
            return const Center(child: Text('تعذر تحميل كشف الحساب.'));
          }
          final s = snapshot.data!;
          return Column(
            children: [
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(16),
                color: Theme.of(context).colorScheme.primaryContainer.withOpacity(0.3),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceAround,
                  children: [
                    _SummaryTile(label: 'الرصيد الافتتاحي', value: '${fmt.format(s.openingBalance)} ج.م'),
                    _SummaryTile(label: 'المستحق له الآن', value: '${fmt.format(s.closingBalance)} ج.م', emphasize: true),
                  ],
                ),
              ),
              Expanded(
                child: s.lines.isEmpty
                    ? const Center(child: Text('لا توجد حركات بعد على هذا المورد'))
                    : ListView.separated(
                        itemCount: s.lines.length,
                        separatorBuilder: (_, __) => const Divider(height: 1),
                        itemBuilder: (context, i) {
                          final line = s.lines[i];
                          final isPurchase = line.credit > 0; // supplier statement: credit = they gave us goods
                          return ListTile(
                            title: Text(line.description),
                            subtitle: Text(line.date),
                            trailing: Column(
                              crossAxisAlignment: CrossAxisAlignment.end,
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Text(
                                  isPurchase ? '+${fmt.format(line.credit)}' : '-${fmt.format(line.debit)}',
                                  style: TextStyle(
                                    fontWeight: FontWeight.bold,
                                    color: isPurchase ? Colors.deepOrange.shade700 : Colors.green.shade700,
                                  ),
                                ),
                                Text('الرصيد: ${fmt.format(line.runningBalance)}',
                                    style: const TextStyle(fontSize: 11, color: Colors.black54)),
                              ],
                            ),
                          );
                        },
                      ),
              ),
            ],
          );
        },
      ),
    );
  }
}

class _SummaryTile extends StatelessWidget {
  const _SummaryTile({required this.label, required this.value, this.emphasize = false});
  final String label;
  final String value;
  final bool emphasize;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Text(label, style: const TextStyle(fontSize: 12, color: Colors.black54)),
        const SizedBox(height: 4),
        Text(value, style: TextStyle(fontSize: emphasize ? 20 : 16, fontWeight: FontWeight.bold)),
      ],
    );
  }
}
