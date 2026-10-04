"use client";
import { MotionConfig, motion } from "framer-motion";

/** Re-mounts on every navigation, so each page fades in. Skipped for reduced-motion users. */
export default function Template({ children }: { children: React.ReactNode }) {
  return (
    <MotionConfig reducedMotion="user">
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.25 }}>
        {children}
      </motion.div>
    </MotionConfig>
  );
}
