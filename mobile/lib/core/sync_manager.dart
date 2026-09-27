import 'dart:async';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/foundation.dart';

import 'api_client.dart';
import 'app_config.dart';
import 'local_store.dart';

/// Phase 6 offline-first sync worker (spec §42/§43).
///
///  * Listens to connectivity changes and flushes the [LocalStore] queue
///    as soon as the device is back online.
///  * Exposes a tiny ChangeNotifier so the HomeShell can show/hide the
///    "غير متصل — سترفع التغييرات تلقائيًا" banner and the pending count.
///
/// Design rule: the queue is FIFO and replays via [ApiClient._post] in the
/// original order, so the server sees the same operation sequence the user
/// performed offline (a payment after its invoice, for example).
class SyncManager extends ChangeNotifier {
  SyncManager._();
  static final SyncManager instance = SyncManager._();

  final LocalStore _store = LocalStore.instance;
  StreamSubscription<List<ConnectivityResult>>? _sub;
  bool _online = true;
  int _pending = 0;
  bool _flushing = false;
  Timer? _retryTimer;

  bool get isOnline => _online;
  int get pendingCount => _pending;

  /// Called once from main() after session restore.
  Future<void> start() async {
    await _refreshPending();
    try {
      _sub = Connectivity().onConnectivityChanged.listen((results) {
        final hasNetwork = results.any((r) => r != ConnectivityResult.none);
        final wasOffline = !_online;
        _online = hasNetwork;
        notifyListeners();
        if (wasOffline && hasNetwork) {
          flush(); // fire-and-forget; errors are swallowed inside
        }
      });
    } catch (_) {
      // Plugin unavailable (e.g. tests): assume online and let flush() be
      // triggered manually by the user via the banner retry button.
      _online = true;
    }
    // Safety net: also retry every 5 minutes in case the connectivity
    // event is missed (some devices report flaky transitions).
    _retryTimer = Timer.periodic(const Duration(minutes: 5), (_) {
      if (_online) flush();
    });
  }

  Future<void> _refreshPending() async {
    _pending = await _store.queueLength();
    notifyListeners();
  }

  Future<int> enqueueOfflineWrite(String endpoint, Map<String, String> params) async {
    final n = await _store.enqueue(endpoint, params);
    _pending = n;
    notifyListeners();
    return n;
  }

  /// Replay queued writes FIFO. Returns how many succeeded.
  Future<int> flush() async {
    if (_flushing) return 0;
    _flushing = true;
    var sent = 0;
    try {
      final writes = await _store.pendingWrites();
      final api = ApiClient(baseUrl: AppConfig.apiBaseUrl);
      for (final w in writes) {
        try {
          await api.sendQueued(w.endpoint, w.params);
          await _store.deleteQueued(w.id);
          sent++;
        } on ApiException catch (e) {
          if (e.statusCode == 401) {
            // Session expired while offline writes waited — stop, keep the
            // queue; the re-login flow will flush it afterwards.
            break;
          }
          if (e.statusCode >= 500) {
            break; // server trouble — retry on the next trigger
          }
          // 4xx (other than 401): the operation itself is invalid — drop it
          // rather than poison the queue forever.
          await _store.deleteQueued(w.id);
        } catch (_) {
          break; // network-level failure — stay queued, retry later
        }
      }
    } finally {
      _flushing = false;
      await _refreshPending();
    }
    return sent;
  }

  @override
  void dispose() {
    _sub?.cancel();
    _retryTimer?.cancel();
    super.dispose();
  }
}
