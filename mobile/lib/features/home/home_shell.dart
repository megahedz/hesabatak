import 'package:flutter/material.dart';
import '../../core/session.dart';
import '../../core/sync_manager.dart';
import '../../ui/theme.dart';
import '../../ui/widgets.dart';
import '../dashboard/dashboard_screen.dart';
import '../invoices/sales_invoice_screen.dart';
import '../invoices/purchase_invoice_screen.dart';
import '../invoices/expenses_screen.dart';
import '../customers/customers_screen.dart';
import '../suppliers/suppliers_screen.dart';
import '../inventory/inventory_screen.dart';
import '../treasury/treasury_screen.dart';
import '../assets/fixed_assets_screen.dart';
import '../reports/reports_screen.dart';
import '../settings/settings_screen.dart';

/// الأقسام الرئيسية الـ 11 (كالتصميم المرجعي تمامًا) — تُعرض في القائمة
/// الجانبية RTL، والقسم النشط يُظلَّل بالأزرق.
class HomeShell extends StatefulWidget {
  const HomeShell({super.key});

  static const sections = <(String, IconData)>[
    ('الرئيسية', Icons.home_rounded),
    ('المبيعات', Icons.receipt_long_rounded),
    ('المشتريات', Icons.shopping_cart_rounded),
    ('المصروفات', Icons.account_balance_wallet_rounded),
    ('العملاء', Icons.people_alt_rounded),
    ('الموردون', Icons.storefront_rounded),
    ('المخزون', Icons.inventory_2_rounded),
    ('الخزنة والبنك', Icons.savings_rounded),
    ('الأصول الثابتة', Icons.domain_rounded),
    ('التقارير', Icons.bar_chart_rounded),
    ('الإعدادات', Icons.settings_rounded),
  ];

  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> {
  String _current = 'الرئيسية';

  @override
  Widget build(BuildContext context) {
    final session = AppSession.instance;
    return Scaffold(
      drawer: AppDrawer(
        sections: HomeShell.sections,
        current: _current,
        onSelect: (s) => setState(() => _current = s),
        userName: session.userName ?? 'مستخدم',
        companyName: session.companyName ?? '',
        onLogout: () => AppSession.instance.logout(),
      ),
      body: Column(
        children: [
          const _SyncBanner(),
          Expanded(child: _buildScreen(_current)),
        ],
      ),
    );
  }

  Widget _buildScreen(String section) {
    switch (section) {
      case 'المبيعات':
        return const SalesInvoiceScreen();
      case 'المشتريات':
        return const PurchaseInvoiceScreen();
      case 'المصروفات':
        return const ExpensesScreen();
      case 'العملاء':
        return const CustomersScreen();
      case 'الموردون':
        return const SuppliersScreen();
      case 'المخزون':
        return const InventoryScreen();
      case 'الخزنة والبنك':
        return const TreasuryScreen();
      case 'الأصول الثابتة':
        return const FixedAssetsScreen();
      case 'التقارير':
        return const ReportsScreen();
      case 'الإعدادات':
        return const SettingsScreen();
      default:
        return const DashboardScreen();
    }
  }
}

/// Phase 6 (spec §42): shown only when there is something to say — the device
/// is offline, or writes are queued waiting to sync. Hidden otherwise so the
/// normal online experience is unchanged.
class _SyncBanner extends StatelessWidget {
  const _SyncBanner();

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: SyncManager.instance,
      builder: (context, _) {
        final sync = SyncManager.instance;
        if (sync.isOnline && sync.pendingCount == 0) return const SizedBox.shrink();
        final offline = !sync.isOnline;
        return Material(
          color: offline ? AppColors.amber : AppColors.green,
          child: SafeArea(
            top: false,
            bottom: false,
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
              child: Row(
                children: [
                  Icon(offline ? Icons.cloud_off : Icons.cloud_sync, size: 16, color: Colors.white),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      offline
                          ? 'غير متصل — سيتم رفع التغييرات تلقائيًا عند عودة الاتصال'
                          : 'جارٍ رفع ${sync.pendingCount} عملية محفوظة…',
                      style: const TextStyle(color: Colors.white, fontSize: 12),
                    ),
                  ),
                  if (!offline && sync.pendingCount > 0)
                    TextButton(
                      onPressed: () => SyncManager.instance.flush(),
                      child: const Text('رفع الآن', style: TextStyle(color: Colors.white)),
                    ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }
}

/// شريط علوي موحد: (زر القائمة أو رجوع) + العنوان + (اختياري) أزرار.
/// كل شاشة تستخدمه لتطابق المرجع.
class AppHeader extends StatelessWidget implements PreferredSizeWidget {
  const AppHeader({super.key, this.title, this.actions = const []});
  final String? title;
  final List<Widget> actions;

  @override
  Size get preferredSize => const Size.fromHeight(kToolbarHeight);

  @override
  Widget build(BuildContext context) {
    final scaffold = Scaffold.maybeOf(context);
    final hasDrawer = scaffold?.hasDrawer ?? false;
    return AppBar(
      centerTitle: true,
      backgroundColor: AppColors.background,
      foregroundColor: AppColors.navy,
      elevation: 0,
      leading: hasDrawer
          ? Builder(
              builder: (ctx) => IconButton(
                icon: const Icon(Icons.menu, color: AppColors.navy),
                onPressed: () => Scaffold.of(ctx).openDrawer(),
              ),
            )
          : const BackButton(),
      title: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (title == 'حساباتك') ...[
            const HesabatakLogo(size: 30),
            const SizedBox(width: 8),
          ],
          Text(title ?? '',
              style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w800, color: AppColors.navy)),
        ],
      ),
      actions: actions,
    );
  }
}
