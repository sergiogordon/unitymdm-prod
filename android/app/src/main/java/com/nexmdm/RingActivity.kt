package com.nexmdm

import android.animation.ValueAnimator
import android.app.NotificationManager
import android.content.Context
import android.hardware.camera2.CameraManager
import android.media.AudioAttributes
import android.media.AudioManager
import android.media.Ringtone
import android.media.RingtoneManager
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.view.View
import android.view.WindowManager
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity

class RingActivity : AppCompatActivity() {
    
    companion object {
        private const val TAG = "RingActivity"
        private const val DEFAULT_DURATION_SECONDS = 30
        private const val RING_NOTIFICATION_ID = 999
    }
    
    private var ringtone: Ringtone? = null
    private var cameraManager: CameraManager? = null
    private var cameraId: String? = null
    private var isFlashlightOn = false
    private val handler = Handler(Looper.getMainLooper())
    private var flashlightRunnable: Runnable? = null
    private var screenFlashAnimator: ValueAnimator? = null
    private lateinit var rootView: View
    private lateinit var countdownText: TextView
    private var durationSeconds = DEFAULT_DURATION_SECONDS
    private var remainingSeconds = DEFAULT_DURATION_SECONDS
    
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_ring)
        
        rootView = findViewById(R.id.ring_root)
        countdownText = findViewById(R.id.countdown_text)
        
        durationSeconds = intent.getIntExtra("duration", DEFAULT_DURATION_SECONDS)
        remainingSeconds = durationSeconds
        
        setupFullscreen()
        setupCameraManager()
        startRinging()
        startFlashlight()
        startScreenFlash()
        startCountdown()
        
        rootView.setOnClickListener {
            Log.d(TAG, "Screen tapped, dismissing ring alert")
            stopAndFinish()
        }
        
        handler.postDelayed({
            stopAndFinish()
        }, (durationSeconds * 1000).toLong())
    }
    
    private fun setupFullscreen() {
        window.addFlags(
            WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON or
            WindowManager.LayoutParams.FLAG_DISMISS_KEYGUARD or
            WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED or
            WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON
        )
        
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O_MR1) {
            setShowWhenLocked(true)
            setTurnScreenOn(true)
        }
        
        window.decorView.systemUiVisibility = (
            View.SYSTEM_UI_FLAG_FULLSCREEN or
            View.SYSTEM_UI_FLAG_HIDE_NAVIGATION or
            View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
        )
        
        supportActionBar?.hide()
    }
    
    private fun setupCameraManager() {
        try {
            cameraManager = getSystemService(Context.CAMERA_SERVICE) as CameraManager
            val cameraIdList = cameraManager?.cameraIdList
            if (cameraIdList != null && cameraIdList.isNotEmpty()) {
                cameraId = cameraIdList[0]
            }
        } catch (e: Exception) {
            Log.e(TAG, "Failed to setup camera manager", e)
        }
    }
    
    private fun startRinging() {
        try {
            val audioManager = getSystemService(Context.AUDIO_SERVICE) as AudioManager
            
            val originalVolume = audioManager.getStreamVolume(AudioManager.STREAM_ALARM)
            val maxVolume = audioManager.getStreamMaxVolume(AudioManager.STREAM_ALARM)
            audioManager.setStreamVolume(AudioManager.STREAM_ALARM, maxVolume, 0)
            
            val notificationUri = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM)
            ringtone = RingtoneManager.getRingtone(applicationContext, notificationUri)
            
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                ringtone?.isLooping = true
            }
            
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
                val audioAttributes = AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_ALARM)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                    .build()
                ringtone?.audioAttributes = audioAttributes
            }
            
            ringtone?.play()
            Log.d(TAG, "Ringtone started")
            
            handler.postDelayed({
                audioManager.setStreamVolume(AudioManager.STREAM_ALARM, originalVolume, 0)
            }, (durationSeconds * 1000).toLong())
            
        } catch (e: Exception) {
            Log.e(TAG, "Failed to start ringtone", e)
        }
    }
    
    private fun startFlashlight() {
        flashlightRunnable = object : Runnable {
            override fun run() {
                try {
                    if (cameraId != null && cameraManager != null) {
                        cameraManager?.setTorchMode(cameraId!!, !isFlashlightOn)
                        isFlashlightOn = !isFlashlightOn
                        handler.postDelayed(this, 500)
                    }
                } catch (e: Exception) {
                    Log.e(TAG, "Failed to toggle flashlight", e)
                }
            }
        }
        handler.post(flashlightRunnable!!)
    }
    
    private fun startScreenFlash() {
        screenFlashAnimator = ValueAnimator.ofFloat(0f, 1f).apply {
            duration = 1000
            repeatCount = ValueAnimator.INFINITE
            repeatMode = ValueAnimator.REVERSE
            
            addUpdateListener { animator ->
                val alpha = animator.animatedValue as Float
                rootView.alpha = 0.7f + (alpha * 0.3f)
            }
            
            start()
        }
    }
    
    private fun startCountdown() {
        val countdownRunnable = object : Runnable {
            override fun run() {
                countdownText.text = "$remainingSeconds"
                remainingSeconds--
                
                if (remainingSeconds >= 0) {
                    handler.postDelayed(this, 1000)
                }
            }
        }
        handler.post(countdownRunnable)
    }
    
    private fun stopAndFinish() {
        try {
            ringtone?.stop()
            
            flashlightRunnable?.let { handler.removeCallbacks(it) }
            
            if (isFlashlightOn && cameraId != null && cameraManager != null) {
                cameraManager?.setTorchMode(cameraId!!, false)
            }
            
            screenFlashAnimator?.cancel()
            
            val notificationManager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            notificationManager.cancel(RING_NOTIFICATION_ID)
            
        } catch (e: Exception) {
            Log.e(TAG, "Error during cleanup", e)
        } finally {
            finish()
        }
    }
    
    override fun onDestroy() {
        super.onDestroy()
        handler.removeCallbacksAndMessages(null)
        try {
            ringtone?.stop()
            if (isFlashlightOn && cameraId != null && cameraManager != null) {
                cameraManager?.setTorchMode(cameraId!!, false)
            }
            screenFlashAnimator?.cancel()
        } catch (e: Exception) {
            Log.e(TAG, "Error in onDestroy", e)
        }
    }
    
    override fun onBackPressed() {
        stopAndFinish()
    }
}
