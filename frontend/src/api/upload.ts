import axios from 'axios'
import { apiClient } from './client'
import type { UploadAudioResponse } from './types'

export const uploadApi = {
  /**
   * Upload an audio file to temporary storage.
   * Returns the server-assigned temp filename used when creating a lesson.
   */
  audio: (file: File, onProgress?: (percent: number) => void) => {
    const formData = new FormData()
    formData.append('file', file)
    return apiClient
      .post<UploadAudioResponse>('/upload/audio', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (e) => {
          if (onProgress && e.total) {
            onProgress(Math.round((e.loaded * 100) / e.total))
          }
        },
      })
      .then((r) => r.data)
  },

  /**
   * Upload a file directly to an R2 presigned URL.
   * Uses a plain axios instance — no auth header, different host.
   */
  toPresignedUrl: (
    url: string,
    file: File,
    contentType: string,
    onProgress?: (percent: number) => void,
  ) =>
    axios.put(url, file, {
      headers: { 'Content-Type': contentType },
      onUploadProgress: (e) => {
        if (onProgress && e.total) {
          onProgress(Math.round((e.loaded * 100) / e.total))
        }
      },
    }),
}
