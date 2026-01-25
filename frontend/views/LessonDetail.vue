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
  CogIcon,
  ChevronDownIcon,
  ChevronUpIcon,
  MagnifyingGlassIcon,
  ChartBarIcon
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

// Source modal state
const showSourceModal = ref(false);
const selectedSourceEditedText = ref('');
const selectedSource = ref(null);
const sefariaText = ref('');
const isLoadingSefaria = ref(false);

// Source stats modal state
const showSourceStatsModal = ref(false);

// Transcript expander state (for edited view)
const expandedTranscriptIndex = ref(null);

// Process tasks modal state
const showProcessModal = ref(false);
const selectedProcesses = ref({
  transcribe: false,
  correct: false,
  edition: false,
  summary: false,
  sources: false
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

// Function to add source markers to edited text
const addSourceMarkers = (text, sources, globalStartIndex = 0) => {
  if (!sources || sources.length === 0) return text;
  
  let markedText = text;
  
  // Helper function to escape special regex characters
  const escapeRegex = (str) => {
    return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  };
  
  // Use cited_excerpt if available (preferred), otherwise fall back to translation_text or original_text
  const sourcesWithText = sources
    .map((source, idx) => {
      // Prefer cited_excerpt as it's the exact text from the edited version
      const sourceText = source.cited_excerpt || source.translation_text || source.original_text;
      if (!sourceText) return null;
      
      // Remove quotes if present (they might be added/removed during editing)
      const cleanSourceText = sourceText.replace(/^["'«»""]|["'«»""]$/g, '').trim();
      if (!cleanSourceText) return null;
      
      // Try case-insensitive search
      const escapedText = escapeRegex(cleanSourceText);
      const regex = new RegExp(escapedText, 'i');
      
      // Check if this text appears in the edited text (case-insensitive)
      if (regex.test(text)) {
        // Find the actual match (preserving original case)
        const match = text.match(regex);
        if (match) {
          return {
            source,
            text: match[0], // Use the actual matched text (preserves case)
            searchText: cleanSourceText,
            index: idx,
            length: cleanSourceText.length
          };
        }
      }
      return null;
    })
    .filter(item => item !== null);
  
  // Sort by text length (longest first) to avoid nested replacements
  sourcesWithText.sort((a, b) => b.length - a.length);
  
  sourcesWithText.forEach((item) => {
    const marker = globalStartIndex + item.index + 1;
    const matchedText = item.text; // Use the actual matched text from the edited text
    
    // Escape the matched text for safe replacement
    const escapedMatch = escapeRegex(matchedText);
    const regex = new RegExp(escapedMatch);
    
    // Create a highlighted version with superscript marker
    const highlighted = `<mark class="bg-yellow-100 dark:bg-yellow-900/30 dark:text-yellow-50 px-0.5 rounded">${matchedText}<sup class="text-indigo-600 dark:text-indigo-400 font-bold ml-0.5">[${marker}]</sup></mark>`;
    
    // Replace first occurrence (preserving case)
    markedText = markedText.replace(regex, highlighted);
  });
  
  return markedText;
};

// Function to highlight matched text in Sefaria text
const highlightMatchedText = (text, matchedText) => {
  if (!text || !matchedText) return text;
  
  // Escape special regex characters in matchedText
  const escapedMatch = matchedText.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  
  // Create a case-insensitive regex to find the match
  const regex = new RegExp(`(${escapedMatch})`, 'gi');
  
  // Replace with highlighted version
  return text.replace(regex, '<mark class="bg-yellow-200 dark:bg-yellow-800/50 dark:text-yellow-100 px-1 rounded font-medium">$1</mark>');
};

// Collect all sources from edited transcript, grouped by type
const allSources = computed(() => {
  if (!props.lesson.edited_transcript) return [];
  
  const typeMap = new Map();
  
  props.lesson.edited_transcript.forEach((part) => {
    if (part.sources && part.sources.length > 0) {
      part.sources.forEach((source) => {
        const type = source.type || 'Unknown';
        
        if (!typeMap.has(type)) {
          typeMap.set(type, []);
        }
        
        // Add this source with its edited part
        typeMap.get(type).push({
          ...source,
          editedPart: part
        });
      });
    }
  });
  
  // Convert to array of types with their sources, sorted by type name
  return Array.from(typeMap.entries())
    .map(([type, sources]) => ({ type, sources }))
    .sort((a, b) => a.type.localeCompare(b.type));
});

// Compute source statistics by type
const sourceStats = computed(() => {
  if (!props.lesson.edited_transcript) return [];
  
  const typeStatsMap = new Map();
  
  props.lesson.edited_transcript.forEach((part) => {
    if (part.sources && part.sources.length > 0) {
      part.sources.forEach((source) => {
        const type = source.type || 'Unknown';
        
        if (!typeStatsMap.has(type)) {
          typeStatsMap.set(type, {
            type,
            total: 0,
            slugRetrieved: 0,
            citationFound: 0,
            checked: 0 // verified with confidence > 90%
          });
        }
        
        const stats = typeStatsMap.get(type);
        stats.total++;
        
        if (source.slug_retrieved === true) {
          stats.slugRetrieved++;
        }
        
        if (source.citation_found === true) {
          stats.citationFound++;
        }
        
        // Checked: citation found AND verification confidence > 90%
        if (source.citation_found === true && 
            source.verification_confidence !== null && 
            source.verification_confidence > 0.9) {
          stats.checked++;
        }
      });
    }
  });
  
  // Convert to array and sort by type name
  return Array.from(typeStatsMap.values())
    .sort((a, b) => a.type.localeCompare(b.type));
});

// Total statistics across all types
const totalStats = computed(() => {
  return sourceStats.value.reduce((acc, stats) => {
    acc.total += stats.total;
    acc.slugRetrieved += stats.slugRetrieved;
    acc.citationFound += stats.citationFound;
    acc.checked += stats.checked;
    return acc;
  }, { total: 0, slugRetrieved: 0, citationFound: 0, checked: 0 });
});

// Compute global source indices for each part
const getGlobalSourceIndex = (partIndex) => {
  if (!props.lesson.edited_transcript) return 0;
  
  let count = 0;
  for (let i = 0; i < partIndex; i++) {
    const part = props.lesson.edited_transcript[i];
    if (part.sources) {
      count += part.sources.length;
    }
  }
  return count;
};

// Available views based on what data exists
const availableViews = computed(() => {
  const views = [];
  if (props.lesson.summary) {
    views.push({ key: 'summary', label: t('lessons.summary') });
  }
  if (props.lesson.edited_transcript) {
    views.push({ key: 'edited', label: t('lessons.editedTranscript') });
  }
  if (allSources.value.length > 0) {
    views.push({ key: 'sources', label: t('lessons.sources') });
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

// Fetch text from Sefaria API
const fetchSefariaText = async (slug) => {
  if (!slug) {
    sefariaText.value = '';
    return;
  }
  
  try {
    isLoadingSefaria.value = true;
    const response = await axios.get(`https://www.sefaria.org/api/texts/${slug}`);
    
    // Extract text from Sefaria response
    let text = '';
    if (response.data.text) {
      const textData = response.data.text;
      if (Array.isArray(textData)) {
        text = textData.map(item => 
          typeof item === 'string' ? item : Array.isArray(item) ? item.join(' ') : String(item)
        ).join('\n');
      } else if (typeof textData === 'string') {
        text = textData;
      }
    } else if (response.data.he) {
      text = response.data.he;
    } else {
      text = JSON.stringify(response.data, null, 2);
    }
    
    sefariaText.value = text;
  } catch (error) {
    console.error('Failed to fetch Sefaria text:', error);
    sefariaText.value = `Error fetching text from Sefaria: ${error.message}`;
  } finally {
    isLoadingSefaria.value = false;
  }
};

// Open source modal with edited part text and source data
const openSourceModal = async (editedPart, source) => {
  selectedSourceEditedText.value = editedPart.text;
  selectedSource.value = source;
  sefariaText.value = '';
  
  // Fetch Sefaria text if slug is available
  if (source.standard_slug) {
    await fetchSefariaText(source.standard_slug);
  }
  
  showSourceModal.value = true;
};

// Toggle transcript expander
const toggleTranscript = (index) => {
  if (expandedTranscriptIndex.value === index) {
    expandedTranscriptIndex.value = null;
  } else {
    expandedTranscriptIndex.value = index;
  }
};

// Get transcript segments for an edited part
const getTranscriptSegments = (part) => {
  const transcript = props.lesson.corrected_transcript || props.lesson.transcript || [];
  return transcript.filter(seg => 
    (seg.start >= part.start && seg.start < part.end) || 
    (seg.end > part.start && seg.end <= part.end) ||
    (seg.start <= part.start && seg.end >= part.end)
  );
};

// Check if an edited part is currently playing
const isEditedPartPlaying = (part) => {
  return isPlaying.value && currentTime.value >= part.start && currentTime.value < part.end;
};

// Toggle play/pause for edited part
const togglePlayEditedPart = (part) => {
  if (!audioPlayer.value) return;
  
  // If this part is currently playing, pause it
  if (isEditedPartPlaying(part)) {
    audioPlayer.value.pause();
    isPlaying.value = false;
  } else {
    // Otherwise, play from the start of this part
    playFromTimestamp(part.start);
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

const downloadEditedPDF = async () => {
  try {
    const response = await axios.get(
      `${API_URL}/lessons/${props.lesson.id}/pdf/edited`,
      { responseType: 'blob' }
    );
    
    // Create download link
    const url = window.URL.createObjectURL(new Blob([response.data]));
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', `${props.lesson.title}_edited.pdf`);
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
  } catch (error) {
    console.error('Failed to download edited PDF:', error);
    alert(t('lessons.downloadFailed'));
  }
};

const downloadSourcesPDF = async () => {
  try {
    const response = await axios.get(
      `${API_URL}/lessons/${props.lesson.id}/pdf/sources`,
      { responseType: 'blob' }
    );
    
    // Create download link
    const url = window.URL.createObjectURL(new Blob([response.data]));
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', `${props.lesson.title}_sources.pdf`);
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
  } catch (error) {
    console.error('Failed to download sources PDF:', error);
    alert(t('lessons.downloadFailed'));
  }
};

const downloadDetailedSourcesPDF = async () => {
  try {
    const response = await axios.get(
      `${API_URL}/lessons/${props.lesson.id}/pdf/sources/detailed`,
      { responseType: 'blob' }
    );
    
    // Create download link
    const url = window.URL.createObjectURL(new Blob([response.data]));
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', `${props.lesson.title}_sources_detailed.pdf`);
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
  } catch (error) {
    console.error('Failed to download detailed sources PDF:', error);
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
    edition: false,
    summary: false,
    sources: false
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
    const taskOrder = ['transcribe', 'correct', 'edition', 'summary', 'sources'];
    
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
      } else if (taskType === 'edition') {
        parameters.segments_per_group = 100;
        parameters.max_concurrency = 10;
      } else if (taskType === 'summary') {
        parameters.use_corrected = true;
        parameters.prompt_type = selectedSummaryPrompt.value;
      }
      
      // Map task type to API task_type
      const taskTypeMap = {
        'transcribe': 'transcription',
        'correct': 'correction',
        'edition': 'edition',
        'summary': 'summary',
        'sources': 'sources'
      };
      
      await axios.post(`${API_URL}/tasks`, {
        task_type: taskTypeMap[taskType],
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
                v-model="selectedProcesses.edition"
                class="w-4 h-4 text-indigo-600 border-gray-300 rounded focus:ring-indigo-500"
              />
              <div>
                <div class="text-sm font-medium text-gray-900 dark:text-white">
                  {{ t('lessons.processEdition') }}
                </div>
                <div class="text-xs text-gray-500 dark:text-gray-400">
                  {{ t('lessons.processEditionDesc') }}
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
            
            <label class="flex items-center gap-3 p-3 rounded-lg border border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700/50 cursor-pointer transition-colors">
              <input
                type="checkbox"
                v-model="selectedProcesses.sources"
                class="w-4 h-4 text-indigo-600 border-gray-300 rounded focus:ring-indigo-500"
              />
              <div class="flex-1">
                <div class="text-sm font-medium text-gray-900 dark:text-white">
                  {{ t('lessons.processSources') }}
                </div>
                <div class="text-xs text-gray-500 dark:text-gray-400">
                  {{ t('lessons.processSourcesDesc') }}
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
              
              <!-- Download Edited PDF Button (show for edited view) -->
              <button
                v-if="activeView === 'edited' && !isEditingSummary"
                @click="downloadEditedPDF"
                class="inline-flex items-center gap-2 px-3 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-md transition-colors"
              >
                <PrinterIcon class="h-4 w-4" />
                {{ t('lessons.downloadPDF') }}
              </button>
              
              <!-- Download Sources PDF Buttons and Stats (show for sources view) -->
              <button
                v-if="activeView === 'sources' && !isEditingSummary"
                @click="showSourceStatsModal = true"
                class="inline-flex items-center gap-2 px-3 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-md transition-colors mr-2"
              >
                <ChartBarIcon class="h-4 w-4" />
                {{ t('lessons.sourceStats') }}
              </button>
              <button
                v-if="activeView === 'sources' && !isEditingSummary"
                @click="downloadSourcesPDF"
                class="inline-flex items-center gap-2 px-3 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-md transition-colors mr-2"
              >
                <PrinterIcon class="h-4 w-4" />
                {{ t('lessons.downloadSourcesPDF') }}
              </button>
              <button
                v-if="activeView === 'sources' && !isEditingSummary"
                @click="downloadDetailedSourcesPDF"
                class="inline-flex items-center gap-2 px-3 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-md transition-colors"
              >
                <PrinterIcon class="h-4 w-4" />
                {{ t('lessons.downloadDetailedSourcesPDF') }}
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
          
          <!-- Sources View -->
          <div v-else-if="activeView === 'sources'">
            <div v-if="allSources.length > 0" class="space-y-6 max-h-[600px] overflow-auto scroll-smooth print:max-h-none">
              <div
                v-for="(typeGroup, typeIndex) in allSources"
                :key="typeIndex"
                class="p-5 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 transition-all"
              >
                <!-- Type Name -->
                <div class="font-semibold text-lg text-gray-900 dark:text-white mb-4 pb-3 border-b border-gray-200 dark:border-gray-700">
                  {{ typeGroup.type }}
                </div>
                
                <!-- Sources List -->
                <div class="space-y-2">
                  <div
                    v-for="(source, sourceIndex) in typeGroup.sources"
                    :key="sourceIndex"
                    @click="openSourceModal(source.editedPart, source)"
                    class="flex items-start gap-3 p-3 rounded-md bg-gray-50 dark:bg-gray-900 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors cursor-pointer"
                  >
                    <!-- Search icon -->
                    <div class="flex-shrink-0 p-1.5 rounded-md text-indigo-600 dark:text-indigo-400">
                      <MagnifyingGlassIcon class="h-4 w-4" />
                    </div>
                    
                    <!-- Work, Reference, Standard Slug, Translation Text, Original Text, and Confidence -->
                    <div class="flex-1 text-sm text-gray-700 dark:text-gray-300">
                      <div class="flex items-center gap-2 flex-wrap mb-1">
                        <span v-if="source.work" class="italic font-medium">{{ source.work }}</span>
                        <span v-if="source.work && source.ref">, </span>
                        <span v-if="source.ref" class="text-gray-500 dark:text-gray-400">{{ source.ref }}</span>
                        <span v-if="source.standard_slug" class="text-xs text-gray-400 dark:text-gray-500 font-mono">({{ source.standard_slug }})</span>
                        <!-- Verification status icon -->
                        <span v-if="source.citation_found === true && source.verification_confidence !== null && source.verification_confidence > 0.9" 
                          class="text-green-600 dark:text-green-400"
                          title="Verified (confidence > 90%)">
                          <CheckIcon class="h-5 w-5" />
                        </span>
                        <span v-else-if="source.citation_found === false || (source.verification_confidence !== null && source.verification_confidence <= 0.9) || source.slug_retrieved === false"
                          class="text-yellow-600 dark:text-yellow-400"
                          :title="source.citation_found === false ? 'Citation not found' : source.verification_confidence !== null ? `Verification confidence: ${(source.verification_confidence * 100).toFixed(0)}%` : 'Not verified'">
                          <ExclamationTriangleIcon class="h-5 w-5" />
                        </span>
                      </div>
                      <div v-if="source.translation_text" class="italic mb-1">
                        "{{ source.translation_text }}"
                      </div>
                      <div v-if="source.original_text" class="text-gray-600 dark:text-gray-400 italic text-xs">
                        <span class="font-medium">Original:</span> "{{ source.original_text }}"
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
            <div v-else class="text-center py-12">
              <p class="text-gray-500 dark:text-gray-400">
                {{ t('lessons.noSources') }}
              </p>
            </div>
          </div>

          <!-- Edited Transcript View -->
          <div v-else-if="activeView === 'edited'">
            <div v-if="lesson.edited_transcript && lesson.edited_transcript.length > 0" class="space-y-4 max-h-[600px] overflow-auto scroll-smooth print:max-h-none">
              <div
                v-for="(part, index) in lesson.edited_transcript"
                :key="index"
                class="py-3 print:py-2"
              >
                <!-- Controls and Text -->
                <div class="flex gap-3">
                  <!-- Play/Pause Button -->
                  <button
                    v-if="audioUrl"
                    @click="togglePlayEditedPart(part)"
                    class="flex-shrink-0 p-1.5 rounded-md hover:bg-indigo-100 dark:hover:bg-indigo-900/30 text-indigo-600 dark:text-indigo-400 transition-colors print:hidden mt-1"
                    :title="isEditedPartPlaying(part) ? t('lessons.pause') : t('lessons.playSegment')"
                  >
                    <PlayIcon v-if="!isEditedPartPlaying(part)" class="h-4 w-4" />
                    <PauseIcon v-else class="h-4 w-4" />
                  </button>
                  
                  <!-- Edited Text -->
                  <div class="flex-1">
                    <div class="prose prose-sm dark:prose-invert max-w-none mb-3">
                      <div 
                        class="text-gray-900 dark:text-gray-100 leading-relaxed whitespace-pre-wrap print:text-black"
                        v-html="addSourceMarkers(renderMarkdown(part.text), part.sources, getGlobalSourceIndex(index))"
                      ></div>
                    </div>
                  </div>
                  
                  <!-- Transcript Toggle Button -->
                  <button
                    @click="toggleTranscript(index)"
                    class="flex-shrink-0 p-1.5 rounded-md hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-500 dark:text-gray-400 hover:text-indigo-600 dark:hover:text-indigo-400 transition-colors print:hidden mt-1"
                    :title="expandedTranscriptIndex === index ? t('lessons.hideTranscript') : t('lessons.showTranscript')"
                  >
                    <ChevronDownIcon v-if="expandedTranscriptIndex !== index" class="h-4 w-4" />
                    <ChevronUpIcon v-else class="h-4 w-4" />
                  </button>
                </div>
                
                <!-- Expandable Transcript Section -->
                <div 
                  v-if="expandedTranscriptIndex === index"
                  class="ml-11 mt-3 p-4 bg-gray-50 dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700 print:hidden"
                >
                  <div class="space-y-3">
                    <!-- Time Range Header -->
                    <div class="flex items-center gap-2 pb-2 border-b border-gray-200 dark:border-gray-700">
                      <ClockIcon class="h-4 w-4 text-gray-400 dark:text-gray-500" />
                      <div class="text-xs text-gray-600 dark:text-gray-400">
                        <span class="font-semibold">{{ t('lessons.timeRange') }}:</span>
                        {{ formatTimestamp(part.start) }} - {{ formatTimestamp(part.end) }}
                      </div>
                    </div>
                    
                    <!-- Transcript Segments -->
                    <div class="space-y-1">
                      <div class="text-xs font-semibold text-gray-700 dark:text-gray-300 mb-2">
                        {{ t('lessons.originalTranscript') }}
                      </div>
                      <div 
                        v-for="(segment, idx) in getTranscriptSegments(part)"
                        :key="idx"
                        class="text-sm text-gray-900 dark:text-gray-100 leading-relaxed"
                      >
                        <span class="text-xs font-mono text-indigo-600 dark:text-indigo-400 mr-2">{{ formatTimestamp(segment.start) }}-{{ formatTimestamp(segment.end) }}</span>{{ segment.text }}
                      </div>
                      <div v-if="getTranscriptSegments(part).length === 0" class="text-sm text-gray-500 dark:text-gray-400 italic py-2">
                        {{ t('lessons.noTranscripts') }}
                      </div>
                    </div>
                  </div>
                </div>
                
                <!-- Sources -->
                <div v-if="part.sources && part.sources.length > 0" class="space-y-2 mt-4 pt-4 border-t border-gray-200 dark:border-gray-700 print:border-gray-300">
                  <div class="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-2">
                    {{ t('lessons.sources') }}
                  </div>
                  <div
                    v-for="(source, srcIndex) in part.sources"
                    :key="srcIndex"
                    @click="openSourceModal(part, source)"
                    class="flex gap-3 p-3 rounded-md bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 print:bg-gray-50 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors print:cursor-default"
                  >
                    <div class="flex-shrink-0 text-green-600 dark:text-green-400 font-bold text-sm">
                      [{{ getGlobalSourceIndex(index) + srcIndex + 1 }}]
                    </div>
                    <div class="flex-1 text-sm">
                      <div class="flex items-center gap-2 mb-1">
                        <div class="font-semibold text-gray-900 dark:text-white">
                          <span v-if="source.type" class="text-gray-600 dark:text-gray-400">{{ source.type }}</span><span v-if="source.type && source.work"> — </span><span v-if="source.work" class="italic">{{ source.work }}</span>
                        </div>
                        <!-- Verification status icon -->
                        <span v-if="source.citation_found === true && source.verification_confidence !== null && source.verification_confidence > 0.9" 
                          class="text-green-600 dark:text-green-400"
                          title="Verified (confidence > 90%)">
                          <CheckIcon class="h-5 w-5" />
                        </span>
                        <span v-else-if="source.citation_found === false || (source.verification_confidence !== null && source.verification_confidence <= 0.9) || source.slug_retrieved === false"
                          class="text-yellow-600 dark:text-yellow-400"
                          :title="source.citation_found === false ? 'Citation not found' : source.verification_confidence !== null ? `Verification confidence: ${(source.verification_confidence * 100).toFixed(0)}%` : 'Not verified'">
                          <ExclamationTriangleIcon class="h-5 w-5" />
                        </span>
                      </div>
                      <div v-if="source.ref" class="text-xs text-gray-500 dark:text-gray-400 mb-1">
                        {{ source.ref }}<span v-if="source.standard_slug" class="text-gray-400 dark:text-gray-500 font-mono ml-2">({{ source.standard_slug }})</span>
                      </div>
                      <div v-if="source.translation_text" class="text-gray-700 dark:text-gray-300 italic mb-1">
                        "{{ source.translation_text }}"
                      </div>
                      <div v-if="source.original_text" class="text-gray-600 dark:text-gray-400 italic text-xs mt-1">
                        <span class="font-medium">Original:</span> "{{ source.original_text }}"
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
            <div v-else class="text-center py-12">
              <p class="text-gray-500 dark:text-gray-400">
                {{ t('lessons.noEditedTranscript') }}
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

    <!-- Source Modal -->
    <Dialog
      :open="showSourceModal"
      @close="showSourceModal = false"
      class="relative z-50"
    >
      <div class="fixed inset-0 bg-black/30" aria-hidden="true" />
      <div class="fixed inset-0 flex items-center justify-center p-4">
        <DialogPanel class="w-full max-w-4xl bg-white dark:bg-gray-800 rounded-xl shadow-2xl max-h-[90vh] overflow-auto">
          <div class="p-6">
            <DialogTitle class="text-xl font-bold text-gray-900 dark:text-white mb-4">
              {{ t('lessons.sourceDetails') }}
            </DialogTitle>
            
            <div class="space-y-6">
              <!-- Edited Part Text -->
              <div class="bg-gray-50 dark:bg-gray-900 p-4 rounded-lg">
                <h3 class="text-lg font-semibold text-gray-900 dark:text-white mb-3">{{ t('lessons.editedText') }}</h3>
                <div class="prose prose-sm dark:prose-invert max-w-none">
                  <div class="text-gray-900 dark:text-gray-100 leading-relaxed whitespace-pre-wrap" v-html="renderMarkdown(selectedSourceEditedText)"></div>
                </div>
              </div>

              <!-- Source Information -->
              <div v-if="selectedSource" class="bg-gray-50 dark:bg-gray-900 p-4 rounded-lg">
                <h3 class="text-lg font-semibold text-gray-900 dark:text-white mb-3">Source Information</h3>
                <div class="space-y-2 text-sm">
                  <div><span class="font-medium text-gray-700 dark:text-gray-300">Type:</span> <span class="text-gray-900 dark:text-white">{{ selectedSource.type || 'N/A' }}</span></div>
                  <div><span class="font-medium text-gray-700 dark:text-gray-300">Work:</span> <span class="text-gray-900 dark:text-white">{{ selectedSource.work || 'N/A' }}</span></div>
                  <div><span class="font-medium text-gray-700 dark:text-gray-300">Reference:</span> <span class="text-gray-900 dark:text-white">{{ selectedSource.ref || 'N/A' }}</span></div>
                  <div><span class="font-medium text-gray-700 dark:text-gray-300">Slug:</span> <span class="text-gray-900 dark:text-white font-mono text-xs">{{ selectedSource.standard_slug || 'N/A' }}</span></div>
                  <div v-if="selectedSource.cited_excerpt">
                    <span class="font-medium text-gray-700 dark:text-gray-300">Cited Excerpt (in edited text):</span>
                    <div class="text-gray-900 dark:text-white mt-1 bg-yellow-50 dark:bg-yellow-900/20 p-2 rounded border border-yellow-200 dark:border-yellow-800">
                      "{{ selectedSource.cited_excerpt }}"
                    </div>
                  </div>
                  <div v-if="selectedSource.original_text">
                    <span class="font-medium text-gray-700 dark:text-gray-300">Original Text:</span>
                    <div class="text-gray-900 dark:text-white italic mt-1">{{ selectedSource.original_text }}</div>
                  </div>
                  <div v-if="selectedSource.translation_text">
                    <span class="font-medium text-gray-700 dark:text-gray-300">Translation Text:</span>
                    <div class="text-gray-900 dark:text-white italic mt-1">{{ selectedSource.translation_text }}</div>
                  </div>
                  <div v-if="selectedSource.confidence !== null && selectedSource.confidence !== undefined">
                    <span class="font-medium text-gray-700 dark:text-gray-300">Initial Confidence:</span>
                    <span :class="[
                      'px-2 py-0.5 rounded text-xs font-medium ml-2',
                      selectedSource.confidence >= 0.7 ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400' :
                      selectedSource.confidence >= 0.4 ? 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-400' :
                      'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400'
                    ]">
                      {{ (selectedSource.confidence * 100).toFixed(0) }}%
                    </span>
                  </div>
                </div>
              </div>

              <!-- Verification Status -->
              <div v-if="selectedSource && selectedSource.slug_retrieved !== null && selectedSource.slug_retrieved !== undefined" class="bg-gray-50 dark:bg-gray-900 p-4 rounded-lg">
                <h3 class="text-lg font-semibold text-gray-900 dark:text-white mb-3">Verification Status</h3>
                <div class="space-y-2 text-sm">
                  <div>
                    <span class="font-medium text-gray-700 dark:text-gray-300">Slug Retrieved:</span>
                    <span :class="selectedSource.slug_retrieved ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'" class="ml-2">
                      {{ selectedSource.slug_retrieved ? '✅ Yes' : '❌ No' }}
                    </span>
                  </div>
                  <div v-if="selectedSource.slug_retrieved">
                    <span class="font-medium text-gray-700 dark:text-gray-300">Citation Found:</span>
                    <span :class="selectedSource.citation_found ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'" class="ml-2">
                      {{ selectedSource.citation_found ? '✅ Yes' : '❌ No' }}
                    </span>
                  </div>
                  <div v-if="selectedSource.verification_confidence !== null && selectedSource.verification_confidence !== undefined">
                    <span class="font-medium text-gray-700 dark:text-gray-300">Verification Confidence:</span>
                    <span :class="[
                      'px-2 py-0.5 rounded text-xs font-medium ml-2',
                      selectedSource.verification_confidence >= 0.7 ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400' :
                      selectedSource.verification_confidence >= 0.4 ? 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-400' :
                      'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400'
                    ]">
                      {{ (selectedSource.verification_confidence * 100).toFixed(0) }}%
                    </span>
                  </div>
                  <div v-if="selectedSource.verification_explanation">
                    <span class="font-medium text-gray-700 dark:text-gray-300">Explanation:</span>
                    <div class="text-gray-900 dark:text-white mt-1">{{ selectedSource.verification_explanation }}</div>
                  </div>
                  <div v-if="selectedSource.matched_text">
                    <span class="font-medium text-gray-700 dark:text-gray-300">Matched Text:</span>
                    <div class="text-gray-900 dark:text-white italic mt-1">{{ selectedSource.matched_text }}</div>
                  </div>
                </div>
              </div>

              <!-- Sefaria Text -->
              <div v-if="selectedSource && selectedSource.standard_slug" class="bg-gray-50 dark:bg-gray-900 p-4 rounded-lg">
                <h3 class="text-lg font-semibold text-gray-900 dark:text-white mb-3">
                  Text from Sefaria ({{ selectedSource.standard_slug }})
                </h3>
                <div v-if="isLoadingSefaria" class="text-center py-4">
                  <div class="text-gray-500 dark:text-gray-400">Loading...</div>
                </div>
                <div v-else-if="sefariaText" class="prose prose-sm dark:prose-invert max-w-none">
                  <div 
                    class="text-gray-900 dark:text-gray-100 leading-relaxed whitespace-pre-wrap max-h-96 overflow-auto"
                    v-html="selectedSource && selectedSource.matched_text ? highlightMatchedText(sefariaText, selectedSource.matched_text) : sefariaText"
                  ></div>
                </div>
                <div v-else class="text-gray-500 dark:text-gray-400 italic">
                  No text available
                </div>
              </div>
            </div>
            
            <div class="mt-6 flex justify-end">
              <button
                @click="showSourceModal = false"
                class="px-4 py-2 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-300 rounded-lg transition-colors"
              >
                {{ t('lessons.close') }}
              </button>
            </div>
          </div>
        </DialogPanel>
      </div>
    </Dialog>

    <!-- Source Stats Modal -->
    <Dialog
      :open="showSourceStatsModal"
      @close="showSourceStatsModal = false"
      class="relative z-50"
    >
      <div class="fixed inset-0 bg-black/30" aria-hidden="true" />
      <div class="fixed inset-0 flex items-center justify-center p-4">
        <DialogPanel class="w-full max-w-4xl bg-white dark:bg-gray-800 rounded-xl shadow-2xl max-h-[90vh] overflow-auto">
          <div class="p-6">
            <DialogTitle class="text-2xl font-bold text-gray-900 dark:text-white mb-6 pb-4 border-b border-gray-200 dark:border-gray-700">
              {{ t('lessons.sourceStatistics') }}
            </DialogTitle>
            
            <div class="space-y-6">
            <!-- Total Statistics -->
            <div class="bg-indigo-50 dark:bg-indigo-900/20 p-4 rounded-lg border border-indigo-200 dark:border-indigo-800">
              <h3 class="text-lg font-semibold text-gray-900 dark:text-white mb-4">
                {{ t('lessons.totalStatistics') }}
              </h3>
              <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div class="text-center">
                  <div class="text-2xl font-bold text-indigo-600 dark:text-indigo-400">
                    {{ totalStats.total }}
                  </div>
                  <div class="text-sm text-gray-600 dark:text-gray-400 mt-1">
                    {{ t('lessons.totalSources') }}
                  </div>
                </div>
                <div class="text-center">
                  <div class="text-2xl font-bold text-blue-600 dark:text-blue-400">
                    {{ totalStats.slugRetrieved }}
                  </div>
                  <div class="text-sm text-gray-600 dark:text-gray-400 mt-1">
                    {{ t('lessons.slugRetrieved') }}
                  </div>
                </div>
                <div class="text-center">
                  <div class="text-2xl font-bold text-green-600 dark:text-green-400">
                    {{ totalStats.citationFound }}
                  </div>
                  <div class="text-sm text-gray-600 dark:text-gray-400 mt-1">
                    {{ t('lessons.citationFound') }}
                  </div>
                </div>
                <div class="text-center">
                  <div class="text-2xl font-bold text-emerald-600 dark:text-emerald-400">
                    {{ totalStats.checked }}
                  </div>
                  <div class="text-sm text-gray-600 dark:text-gray-400 mt-1">
                    {{ t('lessons.checked') }}
                  </div>
                </div>
              </div>
            </div>

            <!-- Statistics by Type -->
            <div>
              <h3 class="text-lg font-semibold text-gray-900 dark:text-white mb-4">
                {{ t('lessons.statisticsByType') }}
              </h3>
              <div class="overflow-x-auto">
                <table class="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                  <thead class="bg-gray-50 dark:bg-gray-900">
                    <tr>
                      <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                        {{ t('lessons.type') }}
                      </th>
                      <th class="px-4 py-3 text-center text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                        {{ t('lessons.total') }}
                      </th>
                      <th class="px-4 py-3 text-center text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                        {{ t('lessons.slugRetrieved') }}
                      </th>
                      <th class="px-4 py-3 text-center text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                        {{ t('lessons.citationFound') }}
                      </th>
                      <th class="px-4 py-3 text-center text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                        {{ t('lessons.checked') }}
                      </th>
                    </tr>
                  </thead>
                  <tbody class="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                    <tr
                      v-for="stats in sourceStats"
                      :key="stats.type"
                      class="hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
                    >
                      <td class="px-4 py-3 whitespace-nowrap text-sm font-medium text-gray-900 dark:text-white">
                        {{ stats.type }}
                      </td>
                      <td class="px-4 py-3 whitespace-nowrap text-sm text-center text-gray-700 dark:text-gray-300">
                        {{ stats.total }}
                      </td>
                      <td class="px-4 py-3 whitespace-nowrap text-sm text-center text-blue-600 dark:text-blue-400">
                        {{ stats.slugRetrieved }}
                        <span v-if="stats.total > 0" class="text-xs text-gray-500 dark:text-gray-400 ml-1">
                          ({{ ((stats.slugRetrieved / stats.total) * 100).toFixed(0) }}%)
                        </span>
                      </td>
                      <td class="px-4 py-3 whitespace-nowrap text-sm text-center text-green-600 dark:text-green-400">
                        {{ stats.citationFound }}
                        <span v-if="stats.total > 0" class="text-xs text-gray-500 dark:text-gray-400 ml-1">
                          ({{ ((stats.citationFound / stats.total) * 100).toFixed(0) }}%)
                        </span>
                      </td>
                      <td class="px-4 py-3 whitespace-nowrap text-sm text-center text-emerald-600 dark:text-emerald-400">
                        {{ stats.checked }}
                        <span v-if="stats.total > 0" class="text-xs text-gray-500 dark:text-gray-400 ml-1">
                          ({{ ((stats.checked / stats.total) * 100).toFixed(0) }}%)
                        </span>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
            </div>
            
            <div class="mt-6 flex justify-end">
              <button
                @click="showSourceStatsModal = false"
                class="px-4 py-2 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-300 rounded-lg transition-colors"
              >
                {{ t('lessons.close') }}
              </button>
            </div>
          </div>
        </DialogPanel>
      </div>
    </Dialog>
  </div>
</template>

