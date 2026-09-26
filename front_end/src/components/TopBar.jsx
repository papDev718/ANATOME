import "../css/TopBar.css";
export default function TopBar({setShowReport, onClearAll}) {

    const handleClearAll = () => {
        if (window.confirm("Are you sure you want to clear all logged pain data?")) {
            onClearAll();
        }
    };

    return (

        <header className="top-bar">

            <div className="logo">

                <div className="logo-icon" aria-hidden="true" />


                <div>

                    <div className="logo-text">
                        ANATOME
                    </div>

                    <div className="logo-tag">
                        Pain Communication Tool
                    </div>

                </div>

            </div>


            <div className="top-bar-actions">


                <button 
                    className="btn btn-secondary btn-sm"
                    onClick={handleClearAll}
                >
                    Clear all
                </button>


                <button
                    className="btn btn-primary btn-sm"
                    onClick={() => setShowReport(true)}
                >
                    Generate report
                </button>


            </div>


        </header>

    );
}
