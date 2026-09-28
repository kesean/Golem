import { useState } from 'react'
import { TOUR_STEPS } from '../lib/tour'
import { Button } from './ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from './ui/dialog'

type TourDialogProps = {
  open: boolean
  onClose: () => void
}

export function TourDialog({ open, onClose }: TourDialogProps) {
  const [step, setStep] = useState(0)

  const currentStep = TOUR_STEPS[step]
  const isLastStep = step === TOUR_STEPS.length - 1

  function handleNext() {
    if (step < TOUR_STEPS.length - 1) {
      setStep(step + 1)
    } else {
      handleClose()
    }
  }

  function handleBack() {
    if (step > 0) {
      setStep(step - 1)
    }
  }

  function handleClose() {
    setStep(0)
    onClose()
  }

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) handleClose() }}>
      <DialogContent
        data-testid="tour-dialog"
        style={{
          position: 'fixed',
          top: '50%',
          left: '50%',
          transform: 'translate(-50%, -50%)',
          backgroundColor: 'var(--bg-card)',
          border: '1px solid var(--border-color)',
          borderRadius: '8px',
          padding: '24px',
          maxWidth: '500px',
          width: '90%',
          boxShadow: '0 4px 6px rgba(0, 0, 0, 0.1)',
          zIndex: 50,
        }}
      >
        <DialogHeader>
          <DialogTitle style={{ color: 'var(--text-primary)' }}>
            {currentStep.title}
          </DialogTitle>
          <DialogDescription style={{ color: 'var(--text-secondary)' }}>
            {currentStep.body}
          </DialogDescription>
          <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '8px' }}>
            Step {step + 1} of {TOUR_STEPS.length}
          </div>
        </DialogHeader>

        <DialogFooter
          style={{
            display: 'flex',
            gap: '8px',
            justifyContent: 'flex-end',
            marginTop: '24px',
          }}
        >
          {!isLastStep && (
            <Button
              onClick={handleClose}
              variant="ghost"
              style={{
                color: 'var(--text-secondary)',
              }}
            >
              Skip
            </Button>
          )}

          {step > 0 && (
            <Button
              onClick={handleBack}
              variant="outline"
              style={{
                borderColor: 'var(--border-color)',
                color: 'var(--text-secondary)',
              }}
            >
              Back
            </Button>
          )}

          <Button
            key="primary-button"
            onClick={handleNext}
            style={{
              backgroundColor: 'var(--accent)',
              color: 'var(--btn-text)',
            }}
          >
            {isLastStep ? 'Done' : 'Next'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
