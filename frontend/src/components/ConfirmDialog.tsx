/**
 * ConfirmDialog
 * ──────────────
 * Modal confirmation dialog with backdrop blur.
 * Used for destructive actions (e.g. Reset Profile).
 */
import { motion, AnimatePresence } from "framer-motion";
import { AlertTriangle, Loader2 } from "lucide-react";
import GlowButton from "./GlowButton";

interface ConfirmDialogProps {
  title:         string;
  message:       string;
  confirmLabel?: string;
  cancelLabel?:  string;
  onConfirm:     () => void;
  onCancel:      () => void;
  loading?:      boolean;
  destructive?:  boolean;
}

const ConfirmDialog = ({
  title,
  message,
  confirmLabel = "Confirm",
  cancelLabel  = "Cancel",
  onConfirm,
  onCancel,
  loading      = false,
  destructive  = false,
}: ConfirmDialogProps) => (
  <AnimatePresence>
    {/* Backdrop */}
    <motion.div
      key="backdrop"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      onClick={!loading ? onCancel : undefined}
      className="fixed inset-0 z-50 flex items-center justify-center px-4
                 bg-black/60 backdrop-blur-sm"
    >
      {/* Panel — stop click propagation so clicking the card doesn't close */}
      <motion.div
        key="panel"
        initial={{ scale: 0.9, opacity: 0, y: 20 }}
        animate={{ scale: 1,   opacity: 1, y: 0  }}
        exit={{    scale: 0.9, opacity: 0, y: 20  }}
        transition={{ type: "spring", damping: 20, stiffness: 300 }}
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-sm glass-card rounded-2xl p-6
                   border border-border shadow-2xl"
      >
        {/* Icon + Title */}
        <div className="flex items-start gap-4 mb-4">
          <div className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0
            ${destructive ? "bg-red-500/20" : "bg-yellow-500/20"}`}>
            <AlertTriangle className={`w-5 h-5 ${destructive ? "text-red-400" : "text-yellow-400"}`} />
          </div>
          <div>
            <h2 className="text-base font-bold text-foreground">{title}</h2>
            <p className="text-sm text-muted-foreground mt-1 leading-relaxed">{message}</p>
          </div>
        </div>

        {/* Actions */}
        <div className="flex gap-3 justify-end mt-5">
          <button
            onClick={onCancel}
            disabled={loading}
            className="px-4 py-2 rounded-lg text-sm font-medium text-muted-foreground
                       border border-border hover:bg-muted/40 transition disabled:opacity-40"
          >
            {cancelLabel}
          </button>

          <GlowButton
            variant={destructive ? "danger" : "primary"}
            onClick={onConfirm}
            disabled={loading}
            className="px-5 py-2 text-sm"
          >
            {loading
              ? <span className="flex items-center gap-2">
                  <Loader2 className="w-4 h-4 animate-spin" /> Resetting...
                </span>
              : confirmLabel}
          </GlowButton>
        </div>
      </motion.div>
    </motion.div>
  </AnimatePresence>
);

export default ConfirmDialog;
