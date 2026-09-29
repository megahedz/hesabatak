import 'package:flutter/material.dart';
import '../../core/api_client.dart';
import '../../core/app_config.dart';
import '../../ui/theme.dart';
import '../../ui/widgets.dart';
import '../home/home_shell.dart';
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
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppHeader(title: 'كشف حساب: ${widget.customerName}', showMenu: false),
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
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
                child: SectionCard(
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceAround,
                    children: [
                      _SummaryTile(label: 'الرصيد الافتتاحي', value: AppFmt.money(s.openingBalance)),
                      _SummaryTile(
                        label: 'الرصيد الحالي',
                        value: AppFmt.money(s.closingBalance),
                        emphasize: true,
                        valueColor: s.closingBalance > 0 ? AppColors.red : AppColors.greenDark,
                      ),
                    ],
                  ),
                ),
              ),
              Expanded(
                child: s.lines.isEmpty
                    ? const Center(child: Text('لا توجد حركات بعد على هذا العميل'))
                    : ListView(
                        padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
                        children: [
                          SectionCard(
                            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                            child: Column(
                              children: [
                                for (final line in s.lines)
                                  Padding(
                                    padding: const EdgeInsets.symmetric(vertical: 6),
                                    child: Row(
                                      children: [
                                        Expanded(
                                          child: Column(
                                            crossAxisAlignment: CrossAxisAlignment.start,
                                            children: [
                                              Text(line.description,
                                                  style: const TextStyle(
                                                      fontSize: 13.5,
                                                      fontWeight: FontWeight.w600,
                                                      color: AppColors.navy)),
                                              Text(line.date,
                                                  style: const TextStyle(
                                                      fontSize: 11.5, color: AppColors.textSecondary)),
                                            ],
                                          ),
                                        ),
                                        const SizedBox(width: 8),
                                        Column(
                                          crossAxisAlignment: CrossAxisAlignment.end,
                                          children: [
                                            Text(
                                              line.debit > 0
                                                  ? '+${AppFmt.num(line.debit)}'
                                                  : '-${AppFmt.num(line.credit)}',
                                              style: TextStyle(
                                                fontSize: 13.5,
                                                fontWeight: FontWeight.w800,
                                                color: line.debit > 0 ? AppColors.amber : AppColors.green,
                                              ),
                                            ),
                                            Text('الرصيد: ${AppFmt.num(line.runningBalance)}',
                                                style: const TextStyle(
                                                    fontSize: 11, color: AppColors.textSecondary)),
                                          ],
                                        ),
                                      ],
                                    ),
                                  ),
                              ],
                            ),
                          ),
                        ],
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
  const _SummaryTile({required this.label, required this.value, this.emphasize = false, this.valueColor});
  final String label;
  final String value;
  final bool emphasize;
  final Color? valueColor;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Text(label, style: const TextStyle(fontSize: 12, color: AppColors.textSecondary)),
        const SizedBox(height: 4),
        Text(value,
            style: TextStyle(
                fontSize: emphasize ? 18 : 15,
                fontWeight: FontWeight.w800,
                color: valueColor ?? AppColors.navy)),
      ],
    );
  }
}
