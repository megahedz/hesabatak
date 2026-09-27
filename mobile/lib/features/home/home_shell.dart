import 'package:flutter/material.dart';
import '../../core/sync_manager.dart';
import '../dashboard/dashboard_screen.dart';
import '../customers/customers_screen.dart';
import '../suppliers/suppliers_screen.dart';
import '../reports/reports_screen.dart';

/// Bottom nav per spec §37: الرئيسية، العملاء، الموردون، التقارير.
/// (العمليات lives as the quick-actions grid on the home screen itself and
/// as the "+" inside each list, rather than a separate tab — with only 4
/// destinations the home screen doesn't feel crowded, and a global "+" tab
/// would just duplicate the quick-actions grid already on الرئيسية.)
class HomeShell extends StatefulWidget {
  const HomeShell({super.key});

  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> {
  int _index = 0;

  static const _screens = [
    DashboardScreen(),
    CustomersScreen(),
    SuppliersScreen(),
    ReportsScreen(),
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Column(
        children: [
          const _SyncBanner(),
          Expanded(child: IndexedStack(index: _index, children: _screens)),
        ],
      ),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: (i) => setState(() => _index = i),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.home_outlined), selectedIcon: Icon(Icons.home), label: 'الرئيسية'),
          NavigationDestination(icon: Icon(Icons.people_outline), selectedIcon: Icon(Icons.people), label: 'العملاء'),
          NavigationDestination(icon: Icon(Icons.local_shipping_outlined), selectedIcon: Icon(Icons.local_shipping), label: 'الموردون'),
          NavigationDestination(icon: Icon(Icons.bar_chart_outlined), selectedIcon: Icon(Icons.bar_chart), label: 'التقارير'),
        ],
      ),
    );
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
          color: offline ? const Color(0xFFB45309) : const Color(0xFF0F6E5C),
          child: SafeArea(
            top: false,
            bottom: false,
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
              child: Row(
                children: [
                  Icon(offline ? Icons.cloud_off : Icons.cloud_sync, size: 16,
                       color: Colors.white),
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
