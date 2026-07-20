import { useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";

export default function Toast({ toast, onDismiss }) {
  const onDismissRef = useRef(onDismiss);
  useEffect(() => {
    onDismissRef.current = onDismiss;
  }, [onDismiss]);

  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => onDismissRef.current(), 4000);
    return () => clearTimeout(timer);
  }, [toast]);

  const idRef = useRef(0);
  const prevToastRef = useRef(toast);
  if (toast !== prevToastRef.current) {
    idRef.current += 1;
    prevToastRef.current = toast;
  }

  return (
    <AnimatePresence>
      {toast && (
        <motion.div
          key={idRef.current}
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 20 }}
          data-testid="toast"
          role="alert"
          aria-live="assertive"
          className={`fixed bottom-6 right-6 px-5 py-3 rounded-xl shadow-lg text-sm font-medium text-white ${
            toast.type === "error"
              ? "bg-status-critical"
              : toast.type === "info"
              ? "bg-ink-secondary"
              : "bg-status-good"
          }`}
        >
          {toast.message}
        </motion.div>
      )}
    </AnimatePresence>
  );
}
