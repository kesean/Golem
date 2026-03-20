import './style.css'
import { askQuestion, clearHistory, initApp } from './app.js'

// Expose for HTML onclick handlers (onclick="askQuestion()" etc.)
window.askQuestion = askQuestion
window.clearHistory = clearHistory

document.addEventListener('DOMContentLoaded', initApp)
