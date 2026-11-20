package com.example

import android.app.Application
import android.os.Build
import android.webkit.WebView

/**
 * Application class ensuring multi-process WebView stability and proper
 * data directory separation between main UI process and background browser worker process.
 */
class PinBoardApplication : Application() {
    override fun onCreate() {
        super.onCreate()
        com.example.util.CrashMonitor.init(this)
        com.example.util.CrashMonitor.addBreadcrumb("Application initialized: ${if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) getProcessName() else "default"}")

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
            val processName = getProcessName()
            if (processName != packageName) {
                val suffix = processName.substringAfterLast(":", "worker")
                try {
                    WebView.setDataDirectorySuffix(suffix)
                } catch (e: Exception) {
                    e.printStackTrace()
                }
            } else {
                try {
                    WebView.setDataDirectorySuffix("main")
                } catch (e: Exception) {
                    e.printStackTrace()
                }
                com.example.util.BackupManager.checkAndPerformScheduledBackup(this)
            }
        } else {
            com.example.util.BackupManager.checkAndPerformScheduledBackup(this)
        }
    }
}
