import 'package:flutter/material.dart';
import '../../core/api_client.dart';
import '../../core/app_config.dart';
import '../../ui/theme.dart';
import '../../ui/widgets.dart';
import '../customers/customer_model.dart'; // shares the Statement/StatementLine model
import '../home/home_shell.dart';

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
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppHeader(title: 'كشف حساب: ${widget.supplierName}', showMenu: false),
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
                        label: 'المستحق له الآن',
                        value: AppFmt.money(s.closingBalance),
                        emphasize: true,
                        valueColor: s.closingBalance > 0 ? AppColors.red : AppColors.green,
                      ),
                    ],
                  ),
                ),
              ),
              Expanded(
                child: s.lines.isEmpty
                    ? const Center(child: Text('لا توجد حركات بعد على هذا المورد'))
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
                                              line.credit > 0
                                                  ? '+${AppFmt.num(line.credit)}'
                                                  : '-${AppFmt.num(line.debit)}',
                                              style: TextStyle(
                                                fontSize: 13.5,
                                                fontWeight: FontWeight.w800,
                                                color: line.credit > 0 ? AppColors.amber : AppColors.green,
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
