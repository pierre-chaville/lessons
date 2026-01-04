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
  PauseIcon,
  PencilIcon,
  CheckIcon,
  XMarkIcon,
  PrinterIcon,
  TrashIcon,
  ExclamationTriangleIcon,
  CogIcon
} from '@heroicons/vue/24/outline';
import { SpeakerWaveIcon } from '@heroicons/vue/24/solid';
import { Dialog, DialogPanel, DialogTitle } from '@headlessui/vue';
import axios from 'axios';

const props = defineProps({
  lesson: {
    type: Object,
    required: true
  },
  autoplayFrom: {
    type: Number,
    required: false,
    default: null
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

// Edit summary state
const isEditingSummary = ref(false);
const editedSummary = ref('');
const isSavingSummary = ref(false);

// Edit lesson state
const isEditingLesson = ref(false);
const editedLesson = ref({
  title: '',
  date: '',
  course_id: null,
  theme_ids: [],
  brief: ''
});
const isSavingLesson = ref(false);

// Edit segment state
const editingSegmentIndex = ref(null);
const editedSegmentText = ref('');
const isSavingSegment = ref(false);

// Delete confirmation state
const showDeleteConfirm = ref(false);
const isDeleting = ref(false);

// Process tasks modal state
const showProcessModal = ref(false);
const selectedProcesses = ref({
  transcribe: false,
  correct: false,
  summary: false
});
const selectedSummaryPrompt = ref('');
const availableSummaryPrompts = ref([]);
const isCreatingTasks = ref(false);

const API_URL = 'http://localhost:8000';

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
  return transcript && Array.isArray(transcript);
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

// Auto-play when requested by parent (e.g., Search results)
watch(
  () => props.autoplayFrom,
  (startTime) => {
    if (startTime === null || startTime === undefined) return;
    nextTick(() => {
      playFromTimestamp(startTime);
    });
  },
  { immediate: true }
);

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
  if (activeView.value !== 'transcript') return -1;
  
  return unifiedTranscript.value.findIndex(segment => 
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
  const date = new Date(dateString);
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
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
  if (props.lesson.transcript || props.lesson.corrected_transcript) {
    views.push({ key: 'transcript', label: t('lessons.transcript') });
  }
  return views;
});

// Unified transcript with correction information
const unifiedTranscript = computed(() => {
  const initialTranscript = props.lesson.transcript || [];
  const correctedTranscript = props.lesson.corrected_transcript || [];
  
  // If no initial transcript, return corrected or empty
  if (!initialTranscript.length) {
    return correctedTranscript.map((seg, index) => ({
      index,
      start: seg.start,
      end: seg.end,
      correctedText: seg.text,
      originalText: null,
      hasDiff: false
    }));
  }
  
  // Map segments with correction info
  return initialTranscript.map((seg, index) => {
    const correctedSeg = correctedTranscript[index];
    const originalText = seg.text;
    const correctedText = correctedSeg ? correctedSeg.text : originalText;
    const hasDiff = correctedSeg && originalText !== correctedText;
    
    return {
      index,
      start: seg.start,
      end: seg.end,
      correctedText,
      originalText: hasDiff ? originalText : null,
      hasDiff
    };
  });
});

// Set initial view to first available
if (availableViews.value.length > 0) {
  activeView.value = availableViews.value[0].key;
}

// Edit summary functions
const startEditSummary = () => {
  editedSummary.value = props.lesson.summary || '';
  isEditingSummary.value = true;
};

const cancelEditSummary = () => {
  isEditingSummary.value = false;
  editedSummary.value = '';
};

const saveSummary = async () => {
  if (isSavingSummary.value) return;
  
  try {
    isSavingSummary.value = true;
    
    await axios.patch(`${API_URL}/lessons/${props.lesson.id}`, {
      summary: editedSummary.value
    });
    
    // Update the lesson object
    props.lesson.summary = editedSummary.value;
    isEditingSummary.value = false;
  } catch (error) {
    console.error('Failed to save summary:', error);
    alert(t('lessons.saveFailed'));
  } finally {
    isSavingSummary.value = false;
  }
};

// Download PDF functions
const downloadSummaryPDF = async () => {
  try {
    const response = await axios.get(`${API_URL}/lessons/${props.lesson.id}/pdf/summary`, {
      responseType: 'blob'
    });
    
    // Create download link
    const url = window.URL.createObjectURL(new Blob([response.data]));
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', `${props.lesson.title}_summary.pdf`);
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
  } catch (error) {
    console.error('Failed to download PDF:', error);
    alert(t('lessons.downloadFailed'));
  }
};

const downloadTranscriptPDF = async () => {
  try {
    // Use corrected transcript if available, otherwise initial
    const transcriptType = props.lesson.corrected_transcript ? 'corrected' : 'initial';
    const response = await axios.get(
      `${API_URL}/lessons/${props.lesson.id}/pdf/transcript?transcript_type=${transcriptType}`,
      { responseType: 'blob' }
    );
    
    // Create download link
    const url = window.URL.createObjectURL(new Blob([response.data]));
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', `${props.lesson.title}_transcript.pdf`);
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
  } catch (error) {
    console.error('Failed to download PDF:', error);
    alert(t('lessons.downloadFailed'));
  }
};

// Edit lesson functions
const startEditLesson = async () => {
  // Fetch courses and themes for the dropdowns if not already loaded
  if (!courses.value || courses.value.length === 0) {
    await fetchCourses();
  }
  if (!themes.value || themes.value.length === 0) {
    await fetchThemes();
  }
  
  editedLesson.value = {
    title: props.lesson.title,
    date: props.lesson.date ? new Date(props.lesson.date).toISOString().slice(0, 10) : '',
    course_id: props.lesson.course_id,
    theme_ids: props.lesson.theme_ids || [],
    brief: props.lesson.brief || ''
  };
  isEditingLesson.value = true;
};

const cancelEditLesson = () => {
  isEditingLesson.value = false;
};

const saveLesson = async () => {
  if (isSavingLesson.value) return;
  
  try {
    isSavingLesson.value = true;
    
    const updateData = {
      title: editedLesson.value.title,
      date: editedLesson.value.date ? new Date(editedLesson.value.date).toISOString() : null,
      course_id: editedLesson.value.course_id,
      theme_ids: editedLesson.value.theme_ids,
      brief: editedLesson.value.brief || null
    };
    
    const response = await axios.patch(`${API_URL}/lessons/${props.lesson.id}`, updateData);
    
    // Update the lesson object
    Object.assign(props.lesson, response.data);
    isEditingLesson.value = false;
  } catch (error) {
    console.error('Failed to save lesson:', error);
    alert(t('lessons.saveFailed'));
  } finally {
    isSavingLesson.value = false;
  }
};

const courses = ref([]);
const themes = ref([]);

const fetchCourses = async () => {
  try {
    const response = await axios.get(`${API_URL}/courses`);
    courses.value = response.data;
  } catch (error) {
    console.error('Failed to fetch courses:', error);
  }
};

const fetchThemes = async () => {
  try {
    const response = await axios.get(`${API_URL}/themes`);
    themes.value = response.data;
  } catch (error) {
    console.error('Failed to fetch themes:', error);
  }
};

const toggleTheme = (themeId) => {
  const index = editedLesson.value.theme_ids.indexOf(themeId);
  if (index === -1) {
    editedLesson.value.theme_ids.push(themeId);
  } else {
    editedLesson.value.theme_ids.splice(index, 1);
  }
};

// Delete lesson functions
const confirmDelete = () => {
  showDeleteConfirm.value = true;
};

const cancelDelete = () => {
  showDeleteConfirm.value = false;
};

const deleteLesson = async () => {
  try {
    isDeleting.value = true;
    
    await axios.delete(`${API_URL}/lessons/${props.lesson.id}`);
    
    // Close confirmation dialog
    showDeleteConfirm.value = false;
    
    // Navigate back to lessons list
    emit('close');
  } catch (error) {
    console.error('Failed to delete lesson:', error);
    alert(t('lessons.deleteFailed'));
  } finally {
    isDeleting.value = false;
  }
};

// Process tasks modal functions
const openProcessModal = async () => {
  // Reset selections
  selectedProcesses.value = {
    transcribe: false,
    correct: false,
    summary: false
  };
  showProcessModal.value = true;
  
  // Load available summary prompts from config
  try {
    const response = await axios.get(`${API_URL}/config`);
    const prompts = response.data?.summary?.prompts || [];
    availableSummaryPrompts.value = prompts;
    // Set default to first prompt
    if (prompts.length > 0 && !selectedSummaryPrompt.value) {
      selectedSummaryPrompt.value = prompts[0].name;
    }
  } catch (error) {
    console.error('Failed to load summary prompts:', error);
  }
};

const closeProcessModal = () => {
  showProcessModal.value = false;
};

const createTasks = async () => {
  const selectedTasks = Object.keys(selectedProcesses.value).filter(
    key => selectedProcesses.value[key]
  );
  
  if (selectedTasks.length === 0) {
    alert(t('lessons.selectAtLeastOneProcess'));
    return;
  }
  
  try {
    isCreatingTasks.value = true;
    
    // Define the correct order for task execution
    const taskOrder = ['transcribe', 'correct', 'summary'];
    
    // Filter selected tasks and sort them by the defined order
    const orderedTasks = taskOrder.filter(task => selectedTasks.includes(task));
    
    // Create tasks sequentially in the correct order
    for (const taskType of orderedTasks) {
      const parameters = {
        lesson_id: props.lesson.id
      };
      
      // Add specific parameters for each task type
      if (taskType === 'correct') {
        parameters.segments_per_group = 100;
        parameters.max_concurrency = 10;
      } else if (taskType === 'summary') {
        parameters.use_corrected = true;
        parameters.prompt_type = selectedSummaryPrompt.value;
      }
      
      await axios.post(`${API_URL}/tasks`, {
        task_type: taskType === 'transcribe' ? 'transcription' : taskType === 'correct' ? 'correction' : 'summary',
        parameters: parameters
      });
    }
    
    // Show success message
    alert(t('lessons.tasksCreated', { count: orderedTasks.length }));
    
    // Close modal
    closeProcessModal();
  } catch (error) {
    console.error('Failed to create tasks:', error);
    alert(t('lessons.tasksCreationFailed'));
  } finally {
    isCreatingTasks.value = false;
  }
};

// Edit segment functions
const startEditSegment = (index, currentText) => {
  editingSegmentIndex.value = index;
  editedSegmentText.value = currentText;
};

const cancelEditSegment = () => {
  editingSegmentIndex.value = null;
  editedSegmentText.value = '';
};

const saveSegment = async () => {
  if (isSavingSegment.value || editingSegmentIndex.value === null) return;
  
  try {
    isSavingSegment.value = true;
    
    // Determine if we're editing corrected or initial transcript
    const hasCorrected = props.lesson.corrected_transcript && props.lesson.corrected_transcript.length > 0;
    const transcriptToUpdate = hasCorrected ? 'corrected_transcript' : 'transcript';
    const segments = hasCorrected ? [...props.lesson.corrected_transcript] : [...props.lesson.transcript];
    
    // Update the segment text
    if (editingSegmentIndex.value < segments.length) {
      segments[editingSegmentIndex.value].text = editedSegmentText.value;
      
      // Send update to backend
      await axios.patch(`${API_URL}/lessons/${props.lesson.id}`, {
        [transcriptToUpdate]: segments
      });
      
      // Update the lesson object
      if (hasCorrected) {
        props.lesson.corrected_transcript = segments;
      } else {
        props.lesson.transcript = segments;
      }
      
      // Clear editing state
      editingSegmentIndex.value = null;
      editedSegmentText.value = '';
    }
  } catch (error) {
    console.error('Failed to save segment:', error);
    alert(t('lessons.saveFailed'));
  } finally {
    isSavingSegment.value = false;
  }
};
</script>

<template>
  <!-- Delete Confirmation Dialog -->
  <Dialog :open="showDeleteConfirm" @close="cancelDelete" class="relative z-50">
    <div class="fixed inset-0 bg-black/30 backdrop-blur-sm" aria-hidden="true" />
    
    <div class="fixed inset-0 flex items-center justify-center p-4">
      <DialogPanel class="mx-auto max-w-md w-full bg-white dark:bg-gray-800 rounded-lg shadow-xl">
        <div class="p-6">
          <div class="flex items-center gap-4 mb-4">
            <div class="flex-shrink-0 w-12 h-12 rounded-full bg-red-100 dark:bg-red-900/30 flex items-center justify-center">
              <ExclamationTriangleIcon class="h-6 w-6 text-red-600 dark:text-red-400" />
            </div>
            <div>
              <DialogTitle class="text-lg font-semibold text-gray-900 dark:text-white">
                {{ t('lessons.deleteConfirmTitle') }}
              </DialogTitle>
              <p class="text-sm text-gray-600 dark:text-gray-400 mt-1">
                {{ t('lessons.deleteConfirmMessage') }}
              </p>
            </div>
          </div>
          
          <p class="text-sm text-gray-700 dark:text-gray-300 mb-6 pl-16">
            <strong>{{ lesson.title }}</strong>
          </p>
          
          <div class="flex justify-end gap-3">
            <button
              @click="cancelDelete"
              :disabled="isDeleting"
              class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-600 rounded-md transition-colors disabled:opacity-50"
            >
              {{ t('lessons.cancel') }}
            </button>
            <button
              @click="deleteLesson"
              :disabled="isDeleting"
              class="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-red-600 hover:bg-red-700 disabled:bg-red-400 rounded-md transition-colors"
            >
              <TrashIcon class="h-4 w-4" />
              {{ isDeleting ? t('lessons.deleting') : t('lessons.deleteConfirm') }}
            </button>
          </div>
        </div>
      </DialogPanel>
    </div>
  </Dialog>

  <!-- Process Tasks Modal -->
  <Dialog :open="showProcessModal" @close="closeProcessModal" class="relative z-50">
    <div class="fixed inset-0 bg-black/30 backdrop-blur-sm" aria-hidden="true" />
    
    <div class="fixed inset-0 flex items-center justify-center p-4">
      <DialogPanel class="mx-auto max-w-md w-full bg-white dark:bg-gray-800 rounded-lg shadow-xl">
        <div class="p-6">
          <div class="flex items-center gap-4 mb-6">
            <div class="flex-shrink-0 w-12 h-12 rounded-full bg-indigo-100 dark:bg-indigo-900/30 flex items-center justify-center">
              <CogIcon class="h-6 w-6 text-indigo-600 dark:text-indigo-400" />
            </div>
            <div>
              <DialogTitle class="text-lg font-semibold text-gray-900 dark:text-white">
                {{ t('lessons.processLessonTitle') }}
              </DialogTitle>
              <p class="text-sm text-gray-600 dark:text-gray-400 mt-1">
                {{ t('lessons.processLessonDescription') }}
              </p>
            </div>
          </div>
          
          <!-- Process Selection -->
          <div class="space-y-3 mb-6">
            <label class="flex items-center gap-3 p-3 rounded-lg border border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700/50 cursor-pointer transition-colors">
              <input
                type="checkbox"
                v-model="selectedProcesses.transcribe"
                class="w-4 h-4 text-indigo-600 border-gray-300 rounded focus:ring-indigo-500"
              />
              <div>
                <div class="text-sm font-medium text-gray-900 dark:text-white">
                  {{ t('lessons.processTranscribe') }}
                </div>
                <div class="text-xs text-gray-500 dark:text-gray-400">
                  {{ t('lessons.processTranscribeDesc') }}
                </div>
              </div>
            </label>
            
            <label class="flex items-center gap-3 p-3 rounded-lg border border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700/50 cursor-pointer transition-colors">
              <input
                type="checkbox"
                v-model="selectedProcesses.correct"
                class="w-4 h-4 text-indigo-600 border-gray-300 rounded focus:ring-indigo-500"
              />
              <div>
                <div class="text-sm font-medium text-gray-900 dark:text-white">
                  {{ t('lessons.processCorrect') }}
                </div>
                <div class="text-xs text-gray-500 dark:text-gray-400">
                  {{ t('lessons.processCorrectDesc') }}
                </div>
              </div>
            </label>
            
            <label class="flex items-center gap-3 p-3 rounded-lg border border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700/50 cursor-pointer transition-colors">
              <input
                type="checkbox"
                v-model="selectedProcesses.summary"
                class="w-4 h-4 text-indigo-600 border-gray-300 rounded focus:ring-indigo-500"
              />
              <div class="flex-1">
                <div class="text-sm font-medium text-gray-900 dark:text-white">
                  {{ t('lessons.processSummary') }}
                </div>
                <div class="text-xs text-gray-500 dark:text-gray-400">
                  {{ t('lessons.processSummaryDesc') }}
                </div>
              </div>
            </label>
            
            <!-- Summary Prompt Type Selection (shown when summary is selected) -->
            <div v-if="selectedProcesses.summary" class="ml-7 -mt-1 mb-2">
              <label class="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                {{ t('lessons.summaryPromptType') }}
              </label>
              <select
                v-model="selectedSummaryPrompt"
                class="w-full max-w-md px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500"
              >
                <option
                  v-for="prompt in availableSummaryPrompts"
                  :key="prompt.name"
                  :value="prompt.name"
                >
                  {{ prompt.name }}
                </option>
              </select>
            </div>
          </div>
          
          <!-- Action Buttons -->
          <div class="flex justify-end gap-3">
            <button
              @click="closeProcessModal"
              :disabled="isCreatingTasks"
              class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-600 rounded-md transition-colors disabled:opacity-50"
            >
              {{ t('lessons.cancel') }}
            </button>
            <button
              @click="createTasks"
              :disabled="isCreatingTasks"
              class="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 rounded-md transition-colors"
            >
              <CogIcon class="h-4 w-4" />
              {{ isCreatingTasks ? t('lessons.creating') : t('lessons.createTasks') }}
            </button>
          </div>
        </div>
      </DialogPanel>
    </div>
  </Dialog>
  
  <div class="bg-gray-50 dark:bg-gray-900 min-h-screen transition-colors">
    <!-- Main Content -->
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <!-- Back Button (no card, just like home page) -->
      <button
        @click="emit('close')"
        class="inline-flex items-center gap-2 text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200 transition-colors mb-6"
      >
        <ArrowLeftIcon class="h-5 w-5" />
        {{ t('lessons.backToList') }}
      </button>
      <!-- Lesson Header -->
      <div class="bg-white dark:bg-gray-800 shadow-sm rounded-lg p-6 mb-6 transition-colors">
        <div class="flex items-start justify-between gap-4 mb-4">
          <div class="flex items-start gap-4 flex-1">
            <DocumentTextIcon class="h-8 w-8 text-indigo-600 dark:text-indigo-400 flex-shrink-0 mt-1" />
            <div class="flex-1">
              <h1 class="text-3xl font-bold text-gray-900 dark:text-white mb-4">
                {{ lesson.title }}
              </h1>
              
              <!-- Brief Summary -->
              <p v-if="lesson.brief" class="text-sm text-gray-600 dark:text-gray-400 mb-4 leading-relaxed">
                {{ lesson.brief }}
              </p>
            
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
          
          <!-- Action Buttons -->
          <div v-if="!isEditingLesson" class="flex gap-2">
            <button
              @click="openProcessModal"
              class="flex-shrink-0 inline-flex items-center gap-2 px-3 py-2 text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 rounded-md transition-colors"
            >
              <CogIcon class="h-4 w-4" />
              {{ t('lessons.processLesson') }}
            </button>
            <button
              @click="startEditLesson"
              class="flex-shrink-0 inline-flex items-center gap-2 px-3 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-md transition-colors"
            >
              <PencilIcon class="h-4 w-4" />
              {{ t('lessons.editLesson') }}
            </button>
            <button
              @click="confirmDelete"
              class="flex-shrink-0 inline-flex items-center gap-2 px-3 py-2 text-sm font-medium text-red-700 dark:text-red-400 bg-red-50 dark:bg-red-900/20 hover:bg-red-100 dark:hover:bg-red-900/30 rounded-md transition-colors"
            >
              <TrashIcon class="h-4 w-4" />
              {{ t('lessons.delete') }}
            </button>
          </div>
        </div>
        
        <!-- Edit Lesson Form -->
        <div v-if="isEditingLesson" class="mt-6 pt-6 border-t border-gray-200 dark:border-gray-700">
          <div class="space-y-4">
            <!-- Title -->
            <div>
              <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                {{ t('lessons.title') }}
              </label>
              <input
                v-model="editedLesson.title"
                type="text"
                class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-900 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
              />
            </div>
            
            <!-- Date -->
            <div>
              <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                {{ t('lessons.date') }}
              </label>
              <input
                v-model="editedLesson.date"
                type="date"
                class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-900 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
              />
            </div>
            
            <!-- Brief -->
            <div>
              <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                {{ t('lessons.brief') }}
              </label>
              <textarea
                v-model="editedLesson.brief"
                :placeholder="t('lessons.briefPlaceholder')"
                rows="3"
                class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-900 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 focus:border-transparent resize-none"
              ></textarea>
            </div>
            
            <!-- Course -->
            <div>
              <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                {{ t('lessons.course') }}
              </label>
              <select
                v-model="editedLesson.course_id"
                class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-900 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
              >
                <option :value="null">{{ t('lessons.noCourse') }}</option>
                <option v-for="course in courses" :key="course.id" :value="course.id">
                  {{ course.name }}
                </option>
              </select>
            </div>
            
            <!-- Themes -->
            <div>
              <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                {{ t('lessons.themes') }}
              </label>
              <div class="flex flex-wrap gap-2">
                <button
                  v-for="theme in themes"
                  :key="theme.id"
                  @click="toggleTheme(theme.id)"
                  :class="[
                    'px-3 py-1.5 rounded-full text-sm font-medium transition-colors',
                    editedLesson.theme_ids.includes(theme.id)
                      ? 'bg-indigo-600 text-white'
                      : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-300 dark:hover:bg-gray-600'
                  ]"
                >
                  {{ theme.name }}
                </button>
              </div>
            </div>
            
            <!-- Action Buttons -->
            <div class="flex gap-3 pt-4">
              <button
                @click="saveLesson"
                :disabled="isSavingLesson"
                class="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 rounded-md transition-colors"
              >
                <CheckIcon class="h-4 w-4" />
                {{ isSavingLesson ? t('lessons.saving') : t('lessons.save') }}
              </button>
              <button
                @click="cancelEditLesson"
                :disabled="isSavingLesson"
                class="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 disabled:opacity-50 rounded-md transition-colors"
              >
                <XMarkIcon class="h-4 w-4" />
                {{ t('lessons.cancel') }}
              </button>
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
            
            <div class="flex items-center gap-3">
              <!-- Download PDF Button (show for summary view) -->
              <button
                v-if="activeView === 'summary' && !isEditingSummary"
                @click="downloadSummaryPDF"
                class="inline-flex items-center gap-2 px-3 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-md transition-colors"
              >
                <PrinterIcon class="h-4 w-4" />
                {{ t('lessons.downloadPDF') }}
              </button>
              
              <!-- Download Transcript PDF Button (show for transcript view) -->
              <button
                v-if="activeView === 'transcript' && !isEditingSummary"
                @click="downloadTranscriptPDF"
                class="inline-flex items-center gap-2 px-3 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-md transition-colors"
              >
                <PrinterIcon class="h-4 w-4" />
                {{ t('lessons.downloadPDF') }}
              </button>
              
              <!-- Edit Button (show for summary view) -->
              <button
                v-if="activeView === 'summary' && !isEditingSummary"
                @click="startEditSummary"
                class="inline-flex items-center gap-2 px-3 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-md transition-colors print:hidden"
              >
                <PencilIcon class="h-4 w-4" />
                {{ t('lessons.edit') }}
              </button>
              
              <!-- Audio Player Controls (show for transcript view) -->
              <div 
                v-if="activeView === 'transcript' && audioUrl"
                class="flex items-center gap-2 print:hidden"
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
          <div v-if="activeView === 'summary'">
            <!-- Edit Mode -->
            <div v-if="isEditingSummary" class="space-y-4">
              <textarea
                v-model="editedSummary"
                class="w-full h-96 px-4 py-3 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-indigo-500 focus:border-transparent resize-none font-mono"
                placeholder="Enter summary in markdown format..."
              ></textarea>
              <div class="flex gap-3">
                <button
                  @click="saveSummary"
                  :disabled="isSavingSummary"
                  class="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 rounded-md transition-colors"
                >
                  <CheckIcon class="h-4 w-4" />
                  {{ isSavingSummary ? t('lessons.saving') : t('lessons.save') }}
                </button>
                <button
                  @click="cancelEditSummary"
                  :disabled="isSavingSummary"
                  class="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 disabled:opacity-50 rounded-md transition-colors"
                >
                  <XMarkIcon class="h-4 w-4" />
                  {{ t('lessons.cancel') }}
                </button>
              </div>
            </div>
            
            <!-- View Mode -->
            <div 
              v-else
              class="prose prose-indigo dark:prose-invert max-w-none"
              v-html="renderMarkdown(lesson.summary)"
            ></div>
          </div>
          
          <!-- Unified Transcript View with Diffs -->
          <div v-else-if="activeView === 'transcript'">
            <div v-if="unifiedTranscript.length > 0" class="space-y-4 max-h-[600px] overflow-auto scroll-smooth print:max-h-none">
              <div
                v-for="segment in unifiedTranscript"
                :key="segment.index"
                :data-segment-index="segment.index"
                :class="[
                  'flex gap-3 p-4 rounded-lg border transition-all print:border-0 print:p-2',
                  isSegmentActive(segment)
                    ? 'bg-indigo-50 dark:bg-indigo-900/20 border-indigo-400 dark:border-indigo-600 print:bg-white'
                    : segment.hasDiff
                      ? 'bg-green-50 dark:bg-green-900/10 border-green-200 dark:border-green-800 hover:border-green-300 dark:hover:border-green-700 print:bg-white'
                      : 'bg-gray-50 dark:bg-gray-900 border-gray-200 dark:border-gray-700 hover:border-indigo-300 dark:hover:border-indigo-700 print:bg-white'
                ]"
              >
                <button
                  v-if="audioUrl"
                  @click="playFromTimestamp(segment.start)"
                  class="flex-shrink-0 p-1.5 rounded-md hover:bg-indigo-100 dark:hover:bg-indigo-900/30 text-indigo-600 dark:text-indigo-400 transition-colors print:hidden"
                  :title="t('lessons.playSegment')"
                >
                  <PlayIcon class="h-4 w-4" />
                </button>
                <div class="flex-shrink-0 text-xs font-mono text-indigo-600 dark:text-indigo-400 font-semibold pt-0.5 print:hidden">
                  {{ formatTimestamp(segment.start) }} - {{ formatTimestamp(segment.end) }}
                </div>
                <div class="flex-1 space-y-2">
                  <!-- Edit Mode -->
                  <div v-if="editingSegmentIndex === segment.index" class="space-y-2">
                    <textarea
                      v-model="editedSegmentText"
                      class="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-indigo-500 focus:border-transparent resize-none"
                      rows="3"
                      @keydown.esc="cancelEditSegment"
                    ></textarea>
                    <div class="flex gap-2">
                      <button
                        @click="saveSegment"
                        :disabled="isSavingSegment"
                        class="inline-flex items-center gap-1 px-2 py-1 text-xs font-medium text-white bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 rounded transition-colors"
                      >
                        <CheckIcon class="h-3 w-3" />
                        {{ isSavingSegment ? t('lessons.saving') : t('lessons.save') }}
                      </button>
                      <button
                        @click="cancelEditSegment"
                        :disabled="isSavingSegment"
                        class="inline-flex items-center gap-1 px-2 py-1 text-xs font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 disabled:opacity-50 rounded transition-colors"
                      >
                        <XMarkIcon class="h-3 w-3" />
                        {{ t('lessons.cancel') }}
                      </button>
                    </div>
                  </div>
                  
                  <!-- View Mode -->
                  <div v-else>
                    <div class="flex items-start gap-2">
                      <div class="flex-1">
                        <!-- Corrected Text -->
                        <div class="text-sm text-gray-900 dark:text-gray-100 print:text-black">
                          <span v-if="segment.hasDiff" class="inline-block px-1.5 py-0.5 text-xs font-semibold text-green-700 dark:text-green-400 bg-green-100 dark:bg-green-900/30 rounded mr-2 print:hidden">
                            {{ t('lessons.corrected') }}
                          </span>
                          {{ segment.correctedText }}
                        </div>
                        
                        <!-- Original Text (if different) -->
                        <div v-if="segment.hasDiff" class="text-sm text-gray-500 dark:text-gray-400 italic pl-4 border-l-2 border-gray-300 dark:border-gray-600 print:hidden mt-2">
                          <span class="inline-block px-1.5 py-0.5 text-xs font-semibold text-gray-600 dark:text-gray-400 bg-gray-200 dark:bg-gray-700 rounded mr-2">
                            {{ t('lessons.original') }}
                          </span>
                          {{ segment.originalText }}
                        </div>
                      </div>
                      
                      <!-- Edit Button -->
                      <button
                        @click="startEditSegment(segment.index, segment.correctedText)"
                        class="flex-shrink-0 p-1 rounded hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-500 dark:text-gray-400 hover:text-indigo-600 dark:hover:text-indigo-400 transition-colors print:hidden"
                        :title="t('lessons.editSegment')"
                      >
                        <PencilIcon class="h-4 w-4" />
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
            <!-- No transcript message -->
            <div v-else class="text-center py-12">
              <p class="text-gray-500 dark:text-gray-400">
                {{ t('lessons.noTranscripts') }}
              </p>
            </div>
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

