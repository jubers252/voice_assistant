/* ============================================
   CENTRALIZED UI - TABBED FRONTEND JAVASCRIPT
   ============================================ */

class TabbedDashboardManager {
    constructor() {
        this.isPlaying = false;
        this.currentTrack = 0;
        this.playlist = [];
        this.io = null;
        this.currentTab = 'camera';
        this.init();
    }

    init() {
        this.setupTabNavigation();
        this.setupEventListeners();
        this.updateClock();
        this.fetchWeather();
        this.initializeSocketIO();
        this.checkAssistantStatus();
        
        // Update every second
        setInterval(() => this.updateClock(), 1000);
        // Fetch weather every 10 minutes
        setInterval(() => this.fetchWeather(), 10 * 60 * 1000);
        // Update system stats every 5 seconds
        setInterval(() => this.fetchSystemStatus(), 5000);
        // Update last update time every second
        setInterval(() => this.updateLastUpdate(), 1000);
        // Poll assistant running/stopped state every 3 seconds
        setInterval(() => this.checkAssistantStatus(), 3000);
        
        this.fetchSystemStatus();
    }

    /* ============================================
       TAB NAVIGATION
       ============================================ */

    setupTabNavigation() {
        const tabButtons = document.querySelectorAll('.tab-btn');
        tabButtons.forEach(btn => {
            btn.addEventListener('click', (e) => {
                const tabName = btn.getAttribute('data-tab');
                this.switchTab(tabName);
            });
        });
    }

    switchTab(tabName) {

        console.log(`[switchTab] Attempting to switch to: ${tabName}`);
        
        // Validate tab name
        const validTabs = ['camera', 'anime', 'weather', 'music', 'automation', 'system'];
        if (!validTabs.includes(tabName)) {
            console.error(`[switchTab] Invalid tab: ${tabName}. Valid options: ${validTabs.join(', ')}`);
            return;
        }
        
        // Hide all tab contents
        const contents = document.querySelectorAll('.tab-content');
        console.log(`[switchTab] Found ${contents.length} tab content elements`);
        contents.forEach(content => {
            content.classList.remove('active');
        });

        // Remove active class from all buttons
        const buttons = document.querySelectorAll('.tab-btn');
        console.log(`[switchTab] Found ${buttons.length} tab buttons`);
        buttons.forEach(btn => btn.classList.remove('active'));

        // Show selected tab content
        const selectedContent = document.getElementById(`${tabName}-content`);
        if (selectedContent) {
            selectedContent.classList.add('active');
            console.log(`[switchTab] ✓ Activated content: ${tabName}-content`);
        } else {
            console.error(`[switchTab] ✗ Tab content not found: ${tabName}-content`);
        }

        // Highlight selected button
        const selectedButton = document.querySelector(`[data-tab="${tabName}"]`);
        if (selectedButton) {
            selectedButton.classList.add('active');
            console.log(`[switchTab] ✓ Activated button: [data-tab="${tabName}"]`);
        } else {
            console.error(`[switchTab] ✗ Tab button not found: [data-tab="${tabName}"]`);
        }

        this.currentTab = tabName;
        console.log(`[switchTab] ✓ Successfully switched to tab: ${tabName}`);
    }

    /* ============================================
       EVENT LISTENERS
       ============================================ */

    setupEventListeners() {
        // Camera controls
        const toggleCamera = document.getElementById('toggleCamera');
        if (toggleCamera) {
            toggleCamera.addEventListener('click', () => this.toggleCamera());
        }

        // Quit / Start buttons
        const quitBtn = document.getElementById('quitBtn');
        if (quitBtn) {
            quitBtn.addEventListener('click', () => this.quitAssistant());
        }

        const startBtn = document.getElementById('startBtn');
        if (startBtn) {
            startBtn.addEventListener('click', () => this.startAssistant());
        }

        // Anime face controls
        const toggleAnimeFace = document.getElementById('toggleAnimeFace');
        if (toggleAnimeFace) {
            toggleAnimeFace.addEventListener('click', () => this.toggleAnimeFace());
        }

        // Music player controls
        const playPauseBtn = document.getElementById('playPauseBtn');
        if (playPauseBtn) {
            playPauseBtn.addEventListener('click', () => this.togglePlayPause());
        }

        const prevBtn = document.getElementById('prevBtn');
        if (prevBtn) {
            prevBtn.addEventListener('click', () => this.previousTrack());
        }

        const nextBtn = document.getElementById('nextBtn');
        if (nextBtn) {
            nextBtn.addEventListener('click', () => this.nextTrack());
        }

        const volumeSlider = document.getElementById('volumeSlider');
        if (volumeSlider) {
            volumeSlider.addEventListener('change', (e) => this.setVolume(e.target.value));
        }

        const progressBar = document.getElementById('progressBar');
        if (progressBar) {
            progressBar.addEventListener('change', (e) => this.seek(e.target.value));
        }

        const togglePlaylist = document.getElementById('togglePlaylist');
        if (togglePlaylist) {
            togglePlaylist.addEventListener('click', () => this.togglePlaylist());
        }

        // Home automation controls
        const automationButtons = document.querySelectorAll('.automation-btn-large');
        automationButtons.forEach(btn => {
            btn.addEventListener('click', (e) => {
                const device = btn.getAttribute('data-device');
                this.toggleDevice(device);
            });
        });
    }

    /* ============================================
       SOCKET.IO INITIALIZATION
       ============================================ */

    initializeSocketIO() {
        try {
            this.io = io({
                reconnection: true,
                reconnectionDelay: 1000,
                reconnectionDelayMax: 5000,
                reconnectionAttempts: 5
            });

            this.io.on('connect', () => {
                console.log('✓ Socket.IO connected');
                console.log('Socket.IO ID:', this.io.id);
                this.updateStatus(true);
            });

            this.io.on('disconnect', () => {
                console.log('✗ Socket.IO disconnected');
                this.updateStatus(false);
            });

            this.io.on('system_status', (data) => {
                this.updateSystemStatusDisplay(data);
            });

            this.io.on('weather_update', (data) => {
                this.updateWeatherDisplay(data);
            });

            this.io.on('music_update', (data) => {
                this.updateMusicDisplay(data);
            });

            this.io.on('device_status', (data) => {
                this.updateDeviceStatus(data);
            });

            this.io.on('switch_tab', (data) => {
                const tab = data.tab;
                console.log(`🎯 Tab switch event received: ${tab}`);
                console.log('Event data:', data);
                if (tab) {
                    this.switchTab(tab);
                    console.log(`✓ Successfully switched to ${tab} tab`);
                } else {
                    console.error('❌ Invalid tab name in switch_tab event');
                }
            });

            this.io.on('error', (error) => {
                console.error('Socket.IO error:', error);
            });
        } catch (error) {
            console.error('Error initializing Socket.IO:', error);
            this.updateStatus(false);
        }
    }

    /* ============================================
       CLOCK & TIME
       ============================================ */

    updateClock() {
        const now = new Date();
        const hours = String(now.getHours()).padStart(2, '0');
        const minutes = String(now.getMinutes()).padStart(2, '0');
        const seconds = String(now.getSeconds()).padStart(2, '0');
        
        const timeDisplay = document.getElementById('currentTime');
        if (timeDisplay && this.currentTab === 'weather') {
            timeDisplay.textContent = `${hours}:${minutes}`;
        }

        const updateTime = document.getElementById('lastUpdate');
        if (updateTime) {
            updateTime.textContent = `${hours}:${minutes}:${seconds}`;
        }
    }

    updateLastUpdate() {
        // Already handled by updateClock
    }

    /* ============================================
       ASSISTANT START / STOP
       ============================================ */

    checkAssistantStatus() {
        fetch('/api/assistant/status')
            .then(response => response.json())
            .then(data => this.updateAssistantStatusUI(data.running))
            .catch(error => console.error('Assistant status error:', error));
    }

    updateAssistantStatusUI(running) {
        const statusEl = document.getElementById('status');
        const startBtn = document.getElementById('startBtn');
        const quitBtn = document.getElementById('quitBtn');

        if (statusEl) {
            statusEl.querySelector('span:last-child').textContent = running ? 'Online' : 'Stopped';
            statusEl.querySelector('.status-dot').style.backgroundColor = running
                ? 'var(--success-color)'
                : 'var(--danger-color)';
        }
        if (startBtn) {
            startBtn.style.display = running ? 'none' : 'flex';
            startBtn.disabled = false;
        }
        if (quitBtn) {
            quitBtn.style.display = running ? 'flex' : 'none';
            quitBtn.disabled = false;
        }
    }

    startAssistant() {
        const startBtn = document.getElementById('startBtn');
        if (startBtn) {
            startBtn.disabled = true;
        }

        fetch('/api/assistant/start', { method: 'POST' })
            .then(response => response.json())
            .then(() => {
                console.log('Assistant start requested');
                setTimeout(() => this.checkAssistantStatus(), 2000);
            })
            .catch(error => console.error('Start request error:', error));
    }

    quitAssistant() {
        if (!confirm('Stop the Voice Assistant? The dashboard will stay open so you can start it again.')) {
            return;
        }

        const quitBtn = document.getElementById('quitBtn');
        if (quitBtn) {
            quitBtn.disabled = true;
        }

        const statusEl = document.getElementById('status');
        if (statusEl) {
            statusEl.querySelector('span:last-child').textContent = 'Stopping...';
        }

        fetch('/api/assistant/stop', { method: 'POST' })
            .then(response => response.json())
            .then(() => {
                console.log('Stop requested - assistant cleanup can take up to ~15s (camera/wake-word/scheduler)');
                setTimeout(() => this.checkAssistantStatus(), 3000);
            })
            .catch(error => console.error('Stop request error:', error));
    }

    /* ============================================
       CAMERA CONTROLS
       ============================================ */

    toggleCamera() {
        const btn = document.getElementById('toggleCamera');
        if (btn) {
            const isOn = btn.querySelector('span').textContent === 'ON';
            btn.querySelector('span').textContent = isOn ? 'OFF' : 'ON';
            this.sendCommand('camera', { action: isOn ? 'stop' : 'start' });
        }
    }

    /* ============================================
       ANIME FACE CONTROLS
       ============================================ */

    toggleAnimeFace() {
        const btn = document.getElementById('toggleAnimeFace');
        if (btn) {
            const isOn = btn.querySelector('span').textContent === 'ON';
            btn.querySelector('span').textContent = isOn ? 'OFF' : 'ON';
            this.sendCommand('anime_face', { action: isOn ? 'stop' : 'start' });
        }
    }

    /* ============================================
       WEATHER
       ============================================ */

    fetchWeather() {
        fetch('/api/weather')
            .then(response => response.json())
            .then(data => this.updateWeatherDisplay(data))
            .catch(error => console.error('Weather fetch error:', error));
    }

    updateWeatherDisplay(data) {
        const tempEl = document.getElementById('temperature');
        const humidityEl = document.getElementById('humidity');
        const conditionEl = document.getElementById('weatherCondition');
        const descEl = document.getElementById('weatherDescription');
        const windEl = document.getElementById('windSpeed');
        const pressureEl = document.getElementById('pressure');

        if (tempEl && data.temperature) {
            tempEl.textContent = `${Math.round(data.temperature)}°C`;
        }
        if (humidityEl && data.humidity) {
            humidityEl.textContent = `${data.humidity}%`;
        }
        if (conditionEl && data.condition) {
            conditionEl.textContent = data.condition;
        }
        if (descEl && data.description) {
            descEl.textContent = data.description;
        }
        if (windEl && data.wind_speed) {
            windEl.textContent = `${data.wind_speed} km/h`;
        }
        if (pressureEl && data.pressure) {
            pressureEl.textContent = `${data.pressure} hPa`;
        }
    }

    /* ============================================
       MUSIC PLAYER
       ============================================ */

    togglePlayPause() {
        this.isPlaying = !this.isPlaying;
        this.updatePlayButton();
        this.sendCommand('music', { action: this.isPlaying ? 'play' : 'pause' });
    }

    previousTrack() {
        this.sendCommand('music', { action: 'previous' });
    }

    nextTrack() {
        this.sendCommand('music', { action: 'next' });
    }

    setVolume(value) {
        const volumeValue = document.getElementById('volumeValue');
        if (volumeValue) {
            volumeValue.textContent = `${value}%`;
        }
        this.sendCommand('music', { action: 'volume', value: parseInt(value) });
    }

    seek(value) {
        this.sendCommand('music', { action: 'seek', value: parseInt(value) });
    }

    togglePlaylist() {
        const container = document.getElementById('playlistContainer');
        if (container) {
            container.classList.toggle('hidden');
            if (!container.classList.contains('hidden')) {
                this.fetchPlaylist();
            }
        }
    }

    fetchPlaylist() {
        fetch('/api/playlist')
            .then(response => response.json())
            .then(data => this.displayPlaylist(data))
            .catch(error => console.error('Playlist fetch error:', error));
    }

    displayPlaylist(data) {
        const playlistItems = document.getElementById('playlistItems');
        if (!playlistItems) return;

        this.playlist = data.tracks || [];
        playlistItems.innerHTML = '';

        if (this.playlist.length === 0) {
            playlistItems.innerHTML = '<li class="loading">No tracks in playlist</li>';
            return;
        }

        this.playlist.forEach((track, index) => {
            const li = document.createElement('li');
            li.textContent = `${track.artist} - ${track.title}`;
            if (index === this.currentTrack) {
                li.classList.add('active');
            }
            li.addEventListener('click', () => this.playTrack(index));
            playlistItems.appendChild(li);
        });
    }

    playTrack(index) {
        this.currentTrack = index;
        this.isPlaying = true;
        this.updatePlayButton();
        this.updatePlaylistHighlight();
        this.sendCommand('music', { action: 'play', track_index: index });
    }

    updatePlayButton() {
        const playBtn = document.getElementById('playPauseBtn');
        if (playBtn) {
            playBtn.querySelector('span').textContent = this.isPlaying ? '⏸️' : '▶️';
        }
    }

    updatePlaylistHighlight() {
        const items = document.querySelectorAll('.playlist-items-large li');
        items.forEach((item, index) => {
            if (index === this.currentTrack) {
                item.classList.add('active');
            } else {
                item.classList.remove('active');
            }
        });
    }

    updateMusicDisplay(data) {
        if (data.title) {
            document.getElementById('trackTitle').textContent = data.title;
        }
        if (data.artist) {
            document.getElementById('trackArtist').textContent = data.artist;
        }
        if (data.album_art) {
            document.getElementById('albumArt').src = data.album_art;
        }
        if (data.is_playing !== undefined) {
            this.isPlaying = data.is_playing;
            this.updatePlayButton();
        }
        if (data.progress !== undefined && data.duration !== undefined) {
            const progressBar = document.getElementById('progressBar');
            const currentTime = document.getElementById('musicCurrentTime');
            if (progressBar && data.duration > 0) {
                progressBar.value = (data.progress / data.duration) * 100;
            }
            if (currentTime) {
                currentTime.textContent = this.formatTime(data.progress);
            }
            
            const duration = document.getElementById('duration');
            if (duration) {
                duration.textContent = this.formatTime(data.duration);
            }
        }
    }

    formatTime(seconds) {
        if (!seconds || isNaN(seconds)) return '0:00';
        const mins = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        return `${mins}:${String(secs).padStart(2, '0')}`;
    }

    /* ============================================
       HOME AUTOMATION
       ============================================ */

    toggleDevice(device) {
        const btn = document.querySelector(`[data-device="${device}"]`);
        if (btn) {
            btn.classList.toggle('active');
            const status = btn.querySelector('.device-status');
            const isActive = btn.classList.contains('active');
            status.textContent = isActive ? 'ON' : 'OFF';
            this.sendCommand('device', { device, action: isActive ? 'on' : 'off' });
        }
    }

    updateDeviceStatus(data) {
        const btn = document.querySelector(`[data-device="${data.device}"]`);
        if (btn) {
            const isActive = data.status === 'on' || data.status === true;
            if (isActive) {
                btn.classList.add('active');
            } else {
                btn.classList.remove('active');
            }
            
            const status = btn.querySelector('.device-status');
            status.textContent = isActive ? 'ON' : 'OFF';
        }
    }

    /* ============================================
       SYSTEM STATUS
       ============================================ */

    fetchSystemStatus() {
        fetch('/api/system_status')
            .then(response => response.json())
            .then(data => this.updateSystemStatusDisplay(data))
            .catch(error => console.error('System status error:', error));
    }

    updateSystemStatusDisplay(data) {
        if (data.cpu_usage !== undefined) {
            const cpuUsage = document.getElementById('cpuUsage');
            const cpuValue = document.getElementById('cpuValue');
            if (cpuUsage && cpuValue) {
                cpuUsage.style.width = `${data.cpu_usage}%`;
                cpuValue.textContent = `${Math.round(data.cpu_usage)}%`;
            }
        }

        if (data.memory_usage !== undefined) {
            const memUsage = document.getElementById('memoryUsage');
            const memValue = document.getElementById('memoryValue');
            if (memUsage && memValue) {
                memUsage.style.width = `${data.memory_usage}%`;
                memValue.textContent = `${Math.round(data.memory_usage)}%`;
            }
        }

        if (data.temperature !== undefined) {
            const tempUsage = document.getElementById('tempUsage');
            const tempValue = document.getElementById('tempValue');
            if (tempUsage && tempValue) {
                const tempPercent = Math.min((data.temperature / 100) * 100, 100);
                tempUsage.style.width = `${tempPercent}%`;
                tempValue.textContent = `${data.temperature}°C`;
            }
        }
    }

    /* ============================================
       UTILITY METHODS
       ============================================ */

    updateStatus(isOnline) {
        const statusIndicator = document.querySelector('.status-indicator');
        const statusDot = document.querySelector('.status-dot');
        
        if (statusIndicator && statusDot) {
            if (isOnline) {
                statusDot.style.backgroundColor = 'var(--success-color)';
                statusIndicator.querySelector('span:last-child').textContent = 'Online';
            } else {
                statusDot.style.backgroundColor = 'var(--danger-color)';
                statusIndicator.querySelector('span:last-child').textContent = 'Offline';
            }
        }
    }

    sendCommand(type, payload) {
        if (this.io && this.io.connected) {
            this.io.emit('command', { type, payload });
        } else {
            console.warn('Socket.IO not connected, using HTTP fallback');
            fetch('/api/command', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ type, payload })
            }).catch(error => console.error('Command error:', error));
        }
    }
}

// Initialize dashboard when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.dashboard = new TabbedDashboardManager();
});
