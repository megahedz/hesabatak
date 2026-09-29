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
import '../operations/quick_actions_sheet.dart';
import '../settings/settings_screen.dart';

/// الأقسام الرئيسية الـ 11 (كالتصميم المرجعي تمامًا) — تُعرض في القائمة
/// الجانبية RTL، والقسم النشط يُظلَّل بالأزرق.
class HomeShell extends StatefulWidget {
  const HomeShell({super.key});

  /// مفتاح موحّد لجذر التطبيق: كل أزرار القائمة الجانبية تفتحه عبره حتى
  /// تعمل من داخل Scaffolds متداخلة (كل شاشة لها Scaffold خاص بها).
  static final GlobalKey<ScaffoldState> scaffoldKey = GlobalKey<ScaffoldState>();

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

  /// يطلقه البار السفلي بعد نجاح أي عملية سريعة حتى تعيد الشاشة الظاهرة
  /// تحميل بياناتها فورًا (إشارة يلتقطها الداشبورد).
  static ValueChanged<String>? onSectionRefresh;

  static void refreshCurrent() {
    final cb = onSectionRefresh;
    if (cb != null) cb('refresh');
  }

  @override
  void initState() {
    super.initState();
    HomeShell.onSectionRefresh = (_) {
      if (mounted) setState(() {}); // إعادة بناء تُجبر الشاشة على إعادة التحميل عبر مفاتيحها
    };
  }

  @override
  void dispose() {
    HomeShell.onSectionRefresh = null;
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final session = AppSession.instance;
    return Scaffold(
      key: HomeShell.scaffoldKey,
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
      // ===== بار سفلي: أزرار العملية الأكثر استخدامًا في متناول الإبهام =====
      bottomNavigationBar: const _QuickBar(),
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
///
/// [showMenu] (افتراضي true) يعرض زر القائمة الذي يفتح الدرج الجذري عبر
/// HomeShell.scaffoldKey — يعمل من داخل أي Scaffold متداخل. الشاشات المفتوحة
/// فوق الـ Shell (كشف حساب مثلًا) تمرر false لتظهر زر رجوع بدلًا منه.
class AppHeader extends StatelessWidget implements PreferredSizeWidget {
  const AppHeader({super.key, this.title, this.actions = const [], this.showMenu = true});
  final String? title;
  final List<Widget> actions;
  final bool showMenu;

  @override
  Size get preferredSize => const Size.fromHeight(kToolbarHeight);

  @override
  Widget build(BuildContext context) {
    return AppBar(
      centerTitle: true,
      backgroundColor: AppColors.background,
      foregroundColor: AppColors.navy,
      elevation: 0,
      automaticallyImplyLeading: false,
      leading: showMenu
          ? IconButton(
              tooltip: 'القائمة الجانبية',
              icon: const Icon(Icons.menu, color: AppColors.navy),
              onPressed: () {
                final root = HomeShell.scaffoldKey.currentState;
                if (root == null || !root.mounted) {
                  ScaffoldMessenger.of(context).showSnackBar(
                    const SnackBar(content: Text('القائمة الجانبية غير متاحة هنا')),
                  );
                  return;
                }
                root.openDrawer();
              },
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

/// البار السفلي السريع: خمس عمليات في متناول الإبهام من أي شاشة —
/// بيع، شراء، مصروف، سداد لعميل (قبض)، استلام من مورد (دفع).
/// كل زر يفتح نفس نماذج العمليات السريعة الموجودة في الرئيسية، وبعد نجاح
/// العملية تعيد الشاشة الحالية تحميل بياناتها عبر [HomeShell.refresh].
class _QuickBar extends StatelessWidget {
  const _QuickBar();

  // (label, icon, color) — parallel lists بدل records لتفادي أي اختلاف إصدار.
  static const _labels = ['بيع', 'شراء', 'مصروف', 'سداد', 'استلام'];
  static const _icons = [
    Icons.point_of_sale_rounded,
    Icons.shopping_cart_rounded,
    Icons.receipt_long_rounded,
    Icons.south_rounded,
    Icons.north_rounded,
  ];
  static const _colors = [
    AppColors.green,
    AppColors.primary,
    AppColors.red,
    AppColors.amber,
    AppColors.teal,
  ];

  /// اسم العملية في showQuickActionSheet لكل زر.
  static const _actionNames = ['بيع', 'شراء', 'مصروف', 'قبض من عميل', 'دفع لمورد'];

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      top: false,
      child: Container(
        decoration: BoxDecoration(
          color: Colors.white,
          boxShadow: [
            BoxShadow(
              color: AppColors.navy.withOpacity(0.07),
              blurRadius: 12,
              offset: const Offset(0, -3),
            ),
          ],
        ),
        child: Row(
          children: [
            for (var i = 0; i < _labels.length; i++)
              Expanded(child: _QuickBarButton(index: i)),
          ],
        ),
      ),
    );
  }
}

class _QuickBarButton extends StatelessWidget {
  const _QuickBarButton({required this.index});
  final int index;

  @override
  Widget build(BuildContext context) {
    final label = _QuickBar._labels[index];
    final icon = _QuickBar._icons[index];
    final color = _QuickBar._colors[index];
    return InkWell(
      borderRadius: BorderRadius.circular(14),
      onTap: () {
        showQuickActionSheet(
          context,
          action: _QuickBar._actionNames[index],
          onDone: () => HomeShell.refreshCurrent(),
        );
      },
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 10),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 40,
              height: 40,
              decoration: BoxDecoration(
                color: color.withOpacity(0.12),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Icon(icon, size: 22, color: color),
            ),
            const SizedBox(height: 4),
            Text(label,
                style: const TextStyle(fontSize: 10.5, fontWeight: FontWeight.w600, color: AppColors.navy)),
          ],
        ),
      ),
    );
  }
}
