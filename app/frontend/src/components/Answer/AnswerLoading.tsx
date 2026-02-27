import { animated, useSpring } from "@react-spring/web";
import { useTranslation } from "react-i18next";

import styles from "./Answer.module.css";
import { AnswerIcon } from "./AnswerIcon";

export const AnswerLoading = () => {
    const { t } = useTranslation();
    const animatedStyles = useSpring({
        from: { opacity: 0 },
        to: { opacity: 1 }
    });

    return (
        <animated.div style={{ ...animatedStyles }}>
            <div className={styles.answerContainer}>
                <div className="flex gap-3">
                    <div className="shrink-0 pt-0.5">
                        <AnswerIcon />
                    </div>
                    <div className="flex-1">
                        <p className={styles.answerText}>
                            {t("generatingAnswer")}
                            <span className={styles.loadingdots} />
                        </p>
                    </div>
                </div>
            </div>
        </animated.div>
    );
};
