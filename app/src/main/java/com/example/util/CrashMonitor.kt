package com.example.util

import android.content.Context
import android.os.Build
import android.os.Process
import android.util.Log
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import java.io.File
import java.io.PrintWriter
import java.io.StringWriter
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.concurrent.ConcurrentLinkedQueue

/**
 * Global Crash Monitor and Diagnostics Logging.
 * Captures, stores, and exposes crashes and error stacktraces
 * so users and developers can inspect the exact cause of any error.
 */
object CrashMonitor {
    private const val TAG = "CrashMonitor"
    private const val PREFS_NAME = "crash_monitor_prefs"
    private const val KEY_LAST_CRASH = "last_crash_trace"
    private const val KEY_LAST_CRASH_TIME = "last_crash_time"

    private val breadcrumbs = ConcurrentLinkedQueue<String>()
    private var defaultHandler: Thread.UncaughtExceptionHandler? = null
    private var isInitialized = false
    private var applicationContext: Context? = null

    private val _lastCrashState = MutableStateFlow<String?>(null)
    val lastCrashState: StateFlow<String?> = _lastCrashState.asStateFlow()

    fun init(context: Context) {
        if (isInitialized) return
        isInitialized = true
        applicationContext = context.applicationContext

        // Check if there is a previous crash stored
        val previous = getLastCrash(context)
        if (!previous.isNullOrBlank()) {
            _lastCrashState.value = previous
            Log.e(TAG, "Loaded previous crash log:\n$previous")
        }

        defaultHandler = Thread.getDefaultUncaughtExceptionHandler()
        Thread.setDefaultUncaughtExceptionHandler { thread, throwable ->
            handleUncaughtException(thread, throwable)
        }
    }

    fun addBreadcrumb(message: String) {
        val time = SimpleDateFormat("HH:mm:ss.SSS", Locale.US).format(Date())
        val entry = "[$time] $message"
        breadcrumbs.add(entry)
        while (breadcrumbs.size > 40) {
            breadcrumbs.poll()
        }
        try {
            Log.d(TAG, "Breadcrumb: $entry")
        } catch (_: Throwable) {}
    }

    private fun isCancellation(throwable: Throwable?): Boolean {
        var curr = throwable
        while (curr != null) {
            val name = curr.javaClass.name
            if (curr is java.util.concurrent.CancellationException ||
                curr is kotlinx.coroutines.CancellationException ||
                name.contains("CancellationException", ignoreCase = true) ||
                name.contains("JobCancellationException", ignoreCase = true)
            ) {
                return true
            }
            curr = curr.cause
        }
        return false
    }

    fun recordException(throwable: Throwable, contextTag: String) {
        if (isCancellation(throwable)) {
            return
        }
        val ctx = applicationContext ?: return
        val trace = buildCrashReport(Thread.currentThread().name, throwable, contextTag)
        saveCrashReport(ctx, trace)
        _lastCrashState.value = trace
        try {
            Log.e(TAG, "Non-fatal exception recorded [$contextTag]:", throwable)
        } catch (_: Throwable) {}
    }

    private fun handleUncaughtException(thread: Thread, throwable: Throwable) {
        if (isCancellation(throwable)) {
            return
        }
        val ctx = applicationContext
        val report = buildCrashReport(thread.name, throwable, "Uncaught Exception")
        Log.e(TAG, "FATAL CRASH DETECTED on thread ${thread.name}:\n$report", throwable)

        if (ctx != null) {
            saveCrashReport(ctx, report)
            try {
                val intent = android.content.Intent().apply {
                    setClassName(ctx.packageName, "com.example.ui.CrashReportActivity")
                    putExtra("extra_crash_report", report)
                    addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK or android.content.Intent.FLAG_ACTIVITY_CLEAR_TASK)
                }
                ctx.startActivity(intent)
                Process.killProcess(Process.myPid())
                System.exit(10)
                return
            } catch (t: Throwable) {
                Log.e(TAG, "Failed to launch CrashReportActivity", t)
            }
        }

        _lastCrashState.value = report

        // Forward to default handler so OS/Android knows about it
        defaultHandler?.uncaughtException(thread, throwable) ?: Process.killProcess(Process.myPid())
    }

    private fun buildCrashReport(threadName: String, throwable: Throwable, contextTag: String): String {
        val sw = StringWriter()
        val pw = PrintWriter(sw)
        throwable.printStackTrace(pw)
        val stackTraceString = sw.toString()

        val timeStr = SimpleDateFormat("yyyy-MM-dd HH:mm:ss.SSS", Locale.US).format(Date())
        val breadcrumbText = breadcrumbs.toList().joinToString("\n  ")

        return buildString {
            appendLine("=== PINBOARD CRASH / ERROR REPORT ===")
            appendLine("Time: $timeStr")
            appendLine("Tag: $contextTag")
            appendLine("Thread: $threadName (ID: ${Thread.currentThread().id})")
            appendLine("Device: ${Build.MANUFACTURER} ${Build.MODEL} (Android ${Build.VERSION.RELEASE}, API ${Build.VERSION.SDK_INT})")
            appendLine("Exception: ${throwable.javaClass.name}")
            appendLine("Message: ${throwable.message ?: "None"}")
            appendLine()
            appendLine("--- BREADCRUMBS ---")
            if (breadcrumbText.isNotBlank()) {
                appendLine("  $breadcrumbText")
            } else {
                appendLine("  (No breadcrumbs recorded)")
            }
            appendLine()
            appendLine("--- STACK TRACE ---")
            appendLine(stackTraceString)
            appendLine("=====================================")
        }
    }

    private fun saveCrashReport(context: Context, report: String) {
        try {
            val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            prefs.edit()
                .putString(KEY_LAST_CRASH, report)
                .putLong(KEY_LAST_CRASH_TIME, System.currentTimeMillis())
                .commit() // Use commit to ensure it's written immediately before process exit

            val file = File(context.cacheDir, "last_crash_log.txt")
            file.writeText(report)
            // Clean up legacy location in filesDir to keep user data compact
            try { File(context.filesDir, "last_crash_log.txt").delete() } catch (_: Throwable) {}
        } catch (e: Exception) {
            Log.e(TAG, "Failed to persist crash report", e)
        }
    }

    fun getLastCrash(context: Context): String? {
        return try {
            val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            val fromPrefs = prefs.getString(KEY_LAST_CRASH, null)
            if (!fromPrefs.isNullOrBlank()) return fromPrefs

            val file = File(context.cacheDir, "last_crash_log.txt")
            if (file.exists()) file.readText() else {
                val legacy = File(context.filesDir, "last_crash_log.txt")
                if (legacy.exists()) legacy.readText() else null
            }
        } catch (e: Exception) {
            null
        }
    }

    fun clearLastCrash(context: Context) {
        try {
            val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
            prefs.edit().remove(KEY_LAST_CRASH).remove(KEY_LAST_CRASH_TIME).apply()
            val file = File(context.cacheDir, "last_crash_log.txt")
            if (file.exists()) file.delete()
            val legacy = File(context.filesDir, "last_crash_log.txt")
            if (legacy.exists()) legacy.delete()
            _lastCrashState.value = null
        } catch (e: Exception) {
            Log.e(TAG, "Failed to clear crash log", e)
        }
    }
}
