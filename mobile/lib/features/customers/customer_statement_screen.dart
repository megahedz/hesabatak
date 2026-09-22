import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import '../../core/api_client.dart';
import '../../core/app_config.dart';
import 'customer_model.dart';

/// كشف حساب العميل (spec §23): رصيد افتتاحي، كل فاتورة ودفعة بالترتيب، رصيد ختامي.
class CustomerStatementScreen extends StatefulWidget {
  const CustomerStatementScreen({super.key, required this.customerId, required this.customerName});
  final int customerId;
  final String customerName;

  @override
  State<CustomerStatementScreen> createState() => _CustomerStatementScreenState();
}

class _CustomerStatementScreenState extends State<CustomerStatementScreen> {
  final _api = ApiClient(baseUrl: AppConfig.apiBaseUrl);
  late Future<Statement> _future;

  @override
  void initState() {
    super.initState();
    _future = _api
        .getCustomerStatement(AppConfig.companyId, widget.customerId)
        .then((json) => Statement.fromCustomerJson(json));
  }

  @override
  Widget build(BuildContext context) {
    final fmt = NumberFormat.decimalPattern('ar_EG');
    return Scaffold(
      appBar: AppBar(title: Text('كشف حساب: ${widget.customerName}')),
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
                    _SummaryTile(
                      label: 'الرصيد الحالي',
                      value: '${fmt.format(s.closingBalance)} ج.م',
                      emphasize: true,
                    ),
                  ],
                ),
              ),
              Expanded(
                child: s.lines.isEmpty
                    ? const Center(child: Text('لا توجد حركات بعد على هذا العميل'))
                    : ListView.separated(
                        itemCount: s.lines.length,
                        separatorBuilder: (_, __) => const Divider(height: 1),
                        itemBuilder: (context, i) {
                          final line = s.lines[i];
                          final isDebit = line.debit > 0;
                          return ListTile(
                            title: Text(line.description),
                            subtitle: Text(line.date),
                            trailing: Column(
                              crossAxisAlignment: CrossAxisAlignment.end,
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Text(
                                  isDebit ? '+${fmt.format(line.debit)}' : '-${fmt.format(line.credit)}',
                                  style: TextStyle(
                                    fontWeight: FontWeight.bold,
                                    color: isDebit ? Colors.orange.shade800 : Colors.green.shade700,
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
