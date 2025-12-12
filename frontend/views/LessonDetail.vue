<script setup>
import { ref, computed, watch, nextTick } from 'vue';
import { useI18n } from 'vue-i18n';
import { marked } from 'marked';
import { 
  ArrowLeftIcon,
  ClockIcon,
  CalendarIcon,
  DocumentTextIcon,
  BookOpenIcon,
  PlayIcon,
  PauseIcon
} from '@heroicons/vue/24/outline';
import { SpeakerWaveIcon } from '@heroicons/vue/24/solid';

const props = defineProps({
  lesson: {
    type: Object,
    required: true
  }
});

const emit = defineEmits(['close']);

const { t } = useI18n();

// Audio player ref and state
const audioPlayer = ref(null);
const isPlaying = ref(false);
const currentTime = ref(0);
const currentSegment = ref(null);

// Toggle between summary, corrected transcript, and initial transcript
const activeView = ref('summary');

// Configure marked options
marked.setOptions({
  breaks: true,
  gfm: true,
});

// Render markdown to HTML
const renderMarkdown = (markdown) => {
  if (!markdown) return '';
  return marked(markdown);
};

// Format seconds to MM:SS format
const formatTimestamp = (seconds) => {
  if (!seconds && seconds !== 0) return '00:00';
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
};

// Check if transcript has segments structure
const hasSegments = (transcript) => {
  return transcript && transcript.segments && Array.isArray(transcript.segments);
};

// Audio file URL
const audioUrl = computed(() => {
  if (!props.lesson.id) return null;
  // Use the lesson-specific audio endpoint
  return `http://localhost:8000/lessons/${props.lesson.id}/audio`;
});

// Play audio from specific timestamp
const playFromTimestamp = (startTime) => {
  if (!audioPlayer.value) {
    console.error('Audio player not available');
    return;
  }
  
  const audio = audioPlayer.value;
  console.log('Attempting to play from timestamp:', startTime, 'seconds');
  console.log('Audio duration:', audio.duration);
  console.log('Audio readyState:', audio.readyState);
  console.log('Audio seekable ranges:', audio.seekable.length > 0 ? `${audio.seekable.start(0)} - ${audio.seekable.end(0)}` : 'none');
  
  // Pause if currently playing
  if (!audio.paused) {
    audio.pause();
  }
  
  // Function to perform the seek and play
  const doSeekAndPlay = () => {
    // Check if we can seek to this position
    if (isNaN(audio.duration) || audio.duration === 0) {
      console.error('Audio duration not available');
      return;
    }
    
    if (startTime > audio.duration) {
      console.error('Start time exceeds audio duration');
      return;
    }
    
    // Check if the range is seekable
    if (audio.seekable.length === 0) {
      console.error('Audio is not seekable yet');
      // Wait for canplay event
      audio.addEventListener('canplay', () => {
        console.log('Canplay fired, retrying seek');
        doSeekAndPlay();
      }, { once: true });
      return;
    }
    
    console.log('Setting currentTime to:', startTime);
    
    // Try seeking with the seeked event
    const handleSeeked = () => {
      console.log('Seeked event fired, currentTime is now:', audio.currentTime);
      audio.play().then(() => {
        console.log('Playing successfully from:', audio.currentTime);
        isPlaying.value = true;
      }).catch(err => {
        console.error('Play failed:', err);
      });
    };
    
    audio.addEventListener('seeked', handleSeeked, { once: true });
    audio.currentTime = startTime;
    console.log('CurrentTime after set:', audio.currentTime);
  };
  
  // Check if metadata and enough data is loaded
  if (audio.readyState >= 2) { // HAVE_CURRENT_DATA or better
    console.log('Audio ready, seeking now');
    doSeekAndPlay();
  } else {
    console.log('Waiting for audio to be ready...');
    audio.addEventListener('canplay', () => {
      console.log('Canplay event fired');
      doSeekAndPlay();
    }, { once: true });
    
    // Ensure audio starts loading
    if (audio.readyState === 0) {
      audio.load();
    }
  }
};

// Toggle play/pause
const togglePlayPause = () => {
  if (!audioPlayer.value) return;
  
  if (isPlaying.value) {
    audioPlayer.value.pause();
    isPlaying.value = false;
  } else {
    audioPlayer.value.play();
    isPlaying.value = true;
  }
};

// Update current time
const updateTime = () => {
  if (audioPlayer.value) {
    currentTime.value = audioPlayer.value.currentTime;
  }
};

// Audio ended
const onAudioEnded = () => {
  isPlaying.value = false;
};

// Check if segment is currently playing
const isSegmentActive = (segment) => {
  return currentTime.value >= segment.start && currentTime.value <= segment.end;
};

// Get currently active segment
const activeSegmentIndex = computed(() => {
  const segments = activeView.value === 'corrected' 
    ? props.lesson.corrected_transcript?.segments 
    : props.lesson.transcript?.segments;
  
  if (!segments) return -1;
  
  return segments.findIndex(segment => 
    currentTime.value >= segment.start && currentTime.value <= segment.end
  );
});

// Auto-scroll to active segment
watch(activeSegmentIndex, (newIndex) => {
  if (newIndex === -1 || !isPlaying.value) return;
  
  nextTick(() => {
    const segmentElement = document.querySelector(`[data-segment-index="${newIndex}"]`);
    if (segmentElement) {
      segmentElement.scrollIntoView({
        behavior: 'smooth',
        block: 'center',
        inline: 'nearest'
      });
    }
  });
});

const formatDate = (dateString) => {
  if (!dateString) return '';
  return new Date(dateString).toLocaleString();
};

const formatDuration = (seconds) => {
  if (!seconds) return t('lessons.noDuration');
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = Math.floor(seconds % 60);
  
  if (hours > 0) {
    return `${hours}h ${minutes}m ${secs}s`;
  } else if (minutes > 0) {
    return `${minutes}m ${secs}s`;
  } else {
    return `${secs}s`;
  }
};

// Available views based on what data exists
const availableViews = computed(() => {
  const views = [];
  if (props.lesson.summary) {
    views.push({ key: 'summary', label: t('lessons.summary') });
  }
  if (props.lesson.corrected_transcript) {
    views.push({ key: 'corrected', label: t('lessons.correctedTranscript') });
  }
  if (props.lesson.transcript) {
    views.push({ key: 'initial', label: t('lessons.initialTranscript') });
  }
  return views;
});

// Set initial view to first available
if (availableViews.value.length > 0) {
  activeView.value = availableViews.value[0].key;
}
</script>

<template>
  <div class="bg-gray-50 dark:bg-gray-900 min-h-screen transition-colors">
    <!-- Header with Back Button -->
    <div class="bg-white dark:bg-gray-800 shadow-sm transition-colors sticky top-0 z-10">
      <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
        <button
          @click="emit('close')"
          class="inline-flex items-center gap-2 text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200 transition-colors"
        >
          <ArrowLeftIcon class="h-5 w-5" />
          {{ t('lessons.backToList') }}
        </button>
      </div>
    </div>

    <!-- Main Content -->
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <!-- Lesson Header -->
      <div class="bg-white dark:bg-gray-800 shadow-sm rounded-lg p-6 mb-6 transition-colors">
        <div class="flex items-start gap-4 mb-4">
          <DocumentTextIcon class="h-8 w-8 text-indigo-600 dark:text-indigo-400 flex-shrink-0 mt-1" />
          <div class="flex-1">
            <h1 class="text-3xl font-bold text-gray-900 dark:text-white mb-4">
              {{ lesson.title }}
            </h1>
            
            <!-- Metadata Grid -->
            <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
              <div class="flex items-center gap-2 text-sm">
                <CalendarIcon class="h-5 w-5 text-gray-400 dark:text-gray-500" />
                <div>
                  <div class="text-xs text-gray-500 dark:text-gray-400">{{ t('lessons.date') }}</div>
                  <div class="font-medium text-gray-900 dark:text-white">
                    {{ formatDate(lesson.date) }}
                  </div>
                </div>
              </div>
              
              <div class="flex items-center gap-2 text-sm">
                <ClockIcon class="h-5 w-5 text-gray-400 dark:text-gray-500" />
                <div>
                  <div class="text-xs text-gray-500 dark:text-gray-400">{{ t('lessons.duration') }}</div>
                  <div class="font-medium text-gray-900 dark:text-white">
                    {{ formatDuration(lesson.duration) }}
                  </div>
                </div>
              </div>
              
              <div v-if="lesson.course" class="flex items-center gap-2 text-sm">
                <BookOpenIcon class="h-5 w-5 text-gray-400 dark:text-gray-500" />
                <div>
                  <div class="text-xs text-gray-500 dark:text-gray-400">{{ t('lessons.course') }}</div>
                  <div class="font-medium text-gray-900 dark:text-white">
                    {{ lesson.course.name }}
                  </div>
                </div>
              </div>
              
              <div class="flex items-center gap-2 text-sm">
                <DocumentTextIcon class="h-5 w-5 text-gray-400 dark:text-gray-500" />
                <div>
                  <div class="text-xs text-gray-500 dark:text-gray-400">{{ t('lessons.file') }}</div>
                  <div class="font-medium text-gray-900 dark:text-white font-mono text-xs">
                    {{ lesson.filename }}
                  </div>
                </div>
              </div>
            </div>

            <!-- Themes -->
            <div v-if="lesson.themes && lesson.themes.length > 0" class="flex flex-wrap gap-2">
              <span
                v-for="theme in lesson.themes"
                :key="theme.id"
                class="inline-flex items-center px-3 py-1 rounded-full text-sm font-medium bg-indigo-100 dark:bg-indigo-900/30 text-indigo-800 dark:text-indigo-300"
              >
                {{ theme.name }}
              </span>
            </div>
          </div>
        </div>
      </div>

      <!-- Content Section with Toggle -->
      <div v-if="availableViews.length > 0" class="bg-white dark:bg-gray-800 shadow-sm rounded-lg overflow-hidden transition-colors">
        <!-- Toggle Switch & Audio Player -->
        <div class="border-b border-gray-200 dark:border-gray-700 p-4">
          <div class="flex items-center justify-between gap-4 flex-wrap">
            <div class="inline-flex rounded-lg bg-gray-100 dark:bg-gray-700 p-1">
              <button
                v-for="view in availableViews"
                :key="view.key"
                @click="activeView = view.key"
                :class="[
                  'px-4 py-2 text-sm font-medium rounded-md transition-all',
                  activeView === view.key
                    ? 'bg-white dark:bg-gray-800 text-indigo-600 dark:text-indigo-400 shadow-sm'
                    : 'text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white'
                ]"
              >
                {{ view.label }}
              </button>
            </div>
            
            <!-- Audio Player Controls (show for transcript views) -->
            <div 
              v-if="(activeView === 'corrected' || activeView === 'initial') && audioUrl"
              class="flex items-center gap-2"
            >
              <SpeakerWaveIcon class="h-5 w-5 text-gray-400 dark:text-gray-500" />
              <button
                @click="togglePlayPause"
                class="inline-flex items-center gap-2 px-3 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-md transition-colors"
              >
                <PlayIcon v-if="!isPlaying" class="h-4 w-4" />
                <PauseIcon v-else class="h-4 w-4" />
                {{ isPlaying ? t('lessons.pause') : t('lessons.play') }}
              </button>
            </div>
          </div>
          
          <!-- Hidden Audio Element -->
          <audio
            v-if="audioUrl"
            ref="audioPlayer"
            :src="audioUrl"
            preload="metadata"
            @timeupdate="updateTime"
            @ended="onAudioEnded"
            @play="isPlaying = true"
            @pause="isPlaying = false"
            @loadedmetadata="console.log('Audio metadata loaded')"
            class="hidden"
          ></audio>
        </div>
        
        <!-- Content Panels -->
        <div class="p-6">
          <!-- Summary View -->
          <div 
            v-if="activeView === 'summary'" 
            class="prose prose-indigo dark:prose-invert max-w-none"
            v-html="renderMarkdown(lesson.summary)"
          ></div>
          
          <!-- Corrected Transcript View -->
          <div v-else-if="activeView === 'corrected'">
            <!-- Segmented View -->
            <div v-if="hasSegments(lesson.corrected_transcript)" class="space-y-4 max-h-[600px] overflow-auto scroll-smooth">
              <div
                v-for="(segment, index) in lesson.corrected_transcript.segments"
                :key="index"
                :data-segment-index="index"
                :class="[
                  'flex gap-3 p-4 rounded-lg border transition-all',
                  isSegmentActive(segment)
                    ? 'bg-indigo-50 dark:bg-indigo-900/20 border-indigo-400 dark:border-indigo-600'
                    : 'bg-gray-50 dark:bg-gray-900 border-gray-200 dark:border-gray-700 hover:border-indigo-300 dark:hover:border-indigo-700'
                ]"
              >
                <button
                  v-if="audioUrl"
                  @click="playFromTimestamp(segment.start)"
                  class="flex-shrink-0 p-1.5 rounded-md hover:bg-indigo-100 dark:hover:bg-indigo-900/30 text-indigo-600 dark:text-indigo-400 transition-colors"
                  :title="t('lessons.playSegment')"
                >
                  <PlayIcon class="h-4 w-4" />
                </button>
                <div class="flex-shrink-0 text-xs font-mono text-indigo-600 dark:text-indigo-400 font-semibold pt-0.5">
                  {{ formatTimestamp(segment.start) }} - {{ formatTimestamp(segment.end) }}
                </div>
                <div class="flex-1 text-sm text-gray-700 dark:text-gray-300">
                  {{ segment.text }}
                </div>
              </div>
            </div>
            <!-- Fallback to JSON view -->
            <pre v-else class="whitespace-pre-wrap text-sm text-gray-700 dark:text-gray-300 bg-gray-50 dark:bg-gray-900 p-4 rounded-lg overflow-auto max-h-[600px]">{{ JSON.stringify(lesson.corrected_transcript, null, 2) }}</pre>
          </div>
          
          <!-- Initial Transcript View -->
          <div v-else-if="activeView === 'initial'">
            <!-- Segmented View -->
            <div v-if="hasSegments(lesson.transcript)" class="space-y-4 max-h-[600px] overflow-auto scroll-smooth">
              <div
                v-for="(segment, index) in lesson.transcript.segments"
                :key="index"
                :data-segment-index="index"
                :class="[
                  'flex gap-3 p-4 rounded-lg border transition-all',
                  isSegmentActive(segment)
                    ? 'bg-indigo-50 dark:bg-indigo-900/20 border-indigo-400 dark:border-indigo-600'
                    : 'bg-gray-50 dark:bg-gray-900 border-gray-200 dark:border-gray-700 hover:border-indigo-300 dark:hover:border-indigo-700'
                ]"
              >
                <button
                  v-if="audioUrl"
                  @click="playFromTimestamp(segment.start)"
                  class="flex-shrink-0 p-1.5 rounded-md hover:bg-indigo-100 dark:hover:bg-indigo-900/30 text-indigo-600 dark:text-indigo-400 transition-colors"
                  :title="t('lessons.playSegment')"
                >
                  <PlayIcon class="h-4 w-4" />
                </button>
                <div class="flex-shrink-0 text-xs font-mono text-indigo-600 dark:text-indigo-400 font-semibold pt-0.5">
                  {{ formatTimestamp(segment.start) }} - {{ formatTimestamp(segment.end) }}
                </div>
                <div class="flex-1 text-sm text-gray-700 dark:text-gray-300">
                  {{ segment.text }}
                </div>
              </div>
            </div>
            <!-- Fallback to JSON view -->
            <pre v-else class="whitespace-pre-wrap text-sm text-gray-700 dark:text-gray-300 bg-gray-50 dark:bg-gray-900 p-4 rounded-lg overflow-auto max-h-[600px]">{{ JSON.stringify(lesson.transcript, null, 2) }}</pre>
          </div>
        </div>
      </div>

      <!-- No Content Message -->
      <div v-else class="bg-white dark:bg-gray-800 shadow-sm rounded-lg p-6 text-center transition-colors">
        <p class="text-gray-500 dark:text-gray-400">
          {{ t('lessons.noContent') }}
        </p>
      </div>
    </div>
  </div>
</template>

