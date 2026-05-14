/**
 * Composable – article discussion thread.
 *
 * Manages loading and posting messages for the per-article
 * discussion panel in the review screen.
 */

import { ref } from 'vue'
import * as api from '../lib/api'
import { SCREENS } from '../constants.js'

/**
 * @param {object}  deps
 * @param {import('vue').ComputedRef}      deps.selectedProject
 * @param {import('vue').ComputedRef}      deps.currentReviewResult
 * @param {import('vue').Ref<string>}      deps.screen
 * @param {Function}                       deps.setFlash
 */
export function useDiscussion({ selectedProject, currentReviewResult, screen, setFlash }) {
  const discussionMessages = ref([])
  const discussionLoading = ref(false)
  const discussionSending = ref(false)
  const discussionMessage = ref('')

  /** Reload the discussion thread for the current article. */
  async function loadDiscussionThread() {
    if (
      !selectedProject.value ||
      !currentReviewResult.value?.article?.id ||
      screen.value !== SCREENS.REVIEW
    ) {
      discussionMessages.value = []
      return
    }

    discussionLoading.value = true
    try {
      discussionMessages.value = await api.listArticleDiscussions({
        project: selectedProject.value.id,
        article: currentReviewResult.value.article.id,
      })
    } catch (e) {
      setFlash('', e.message)
    } finally {
      discussionLoading.value = false
    }
  }

  /** Post a new message to the current article's discussion. */
  async function sendDiscussionMessage() {
    if (!selectedProject.value || !currentReviewResult.value?.article?.id) return
    const message = discussionMessage.value.trim()
    if (!message) {
      setFlash('', 'Write a message before sending it')
      return
    }

    discussionSending.value = true
    try {
      await api.createArticleDiscussionMessage({
        project: selectedProject.value.id,
        article: currentReviewResult.value.article.id,
        message,
      })
      discussionMessage.value = ''
      await loadDiscussionThread()
    } catch (e) {
      setFlash('', e.message)
    } finally {
      discussionSending.value = false
    }
  }

  return {
    discussionMessages,
    discussionLoading,
    discussionSending,
    discussionMessage,
    loadDiscussionThread,
    sendDiscussionMessage,
  }
}
