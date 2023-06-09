(function() {

// Localize jQuery variable
var jQuery;
let script = document.querySelector("script[src$='/static/widget/simple_search.js']");
let parser = document.createElement('a');
parser.href = script.attributes.src.value;
let doaj_url = parser.protocol + '//' + parser.host;

    /******** Load scripts *********/

    let head = document.head || document.getElementsByTagName('head')[0];

    let scr = document.createElement('link');
    scr.rel = 'stylesheet';
    scr.href = doaj_url + '/static/doaj/css/simple_widget.css';
    head.appendChild(scr);

    scr  = document.createElement('script');
    scr.src = doaj_url + '/static/vendor/feather-4.28.0/feather.min.js';
//scr.src = 'https://unpkg.com/feather-icons';
    scr.async = false;
    scr.defer = false;
    head.appendChild(scr);


    /******** Load jQuery if not present *********/
    if (window.jQuery === undefined || window.jQuery.fn.jquery !== '3.4.1') {
        var script_tag = document.createElement('script');
        script_tag.setAttribute("type","text/javascript");
        script_tag.setAttribute("src", doaj_url + '/static/vendor/jquery-3.4.1/jquery-3.4.1.min.js');
        if (script_tag.readyState) {
            script_tag.onreadystatechange = function () { // For old versions of IE
                if (this.readyState === 'complete' || this.readyState === 'loaded') {
                    scriptLoadHandler();
                }
            };
        } else { // Other browsers
            script_tag.onload = scriptLoadHandler;
        }
        // Try to find the head, otherwise default to the documentElement
        (document.getElementsByTagName("head")[0] || document.documentElement).appendChild(script_tag);
    } else {
        // The jQuery version on the window is the one we want to use
        jQuery = window.jQuery;
        main();
    }

    /******** Called once jQuery has loaded ******/
    function scriptLoadHandler() {
        // Restore $ and window.jQuery to their previous values and store the
        // new jQuery in our local jQuery variable
        jQuery = window.jQuery.noConflict(true);
        // Call our main function
        main();
    }

    /******** Our main function ********/
    function main() {
        jQuery(document).ready(function($) {

            let html = `
    <form role="search" id="doaj-search-form" method="POST">
        <h2>
            <a href="https://doaj.org/" target="_blank" rel="noopener">
                <svg height="30px" viewBox="0 0 149 53" version="1.1" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">
                    <title>DOAJ</title>
                    <g id="logotype" fill="#282624" fill-rule="nonzero">
                        <path d="M0,0.4219 L17.9297,0.4219 C24.8672,0.4688 30.0703,3.3516 33.5391,9.0703 C34.7812,10.9922 35.5664,13.0078 35.8945,15.1172 C36.1523,17.2266 36.2812,20.8711 36.2812,26.0508 C36.2812,31.5586 36.082,35.4023 35.6836,37.582 C35.4961,38.6836 35.2148,39.668 34.8398,40.5352 C34.4414,41.3789 33.9609,42.2578 33.3984,43.1719 C31.8984,45.5859 29.8125,47.5781 27.1406,49.1484 C24.4922,50.8359 21.2461,51.6797 17.4023,51.6797 L0,51.6797 L0,0.4219 Z M7.7695,44.332 L17.0508,44.332 C21.4102,44.332 24.5742,42.8438 26.543,39.8672 C27.4102,38.7656 27.9609,37.3711 28.1953,35.6836 C28.4062,34.0195 28.5117,30.9023 28.5117,26.332 C28.5117,21.8789 28.4062,18.6914 28.1953,16.7695 C27.9141,14.8477 27.2461,13.2891 26.1914,12.0938 C24.0352,9.1172 20.9883,7.6758 17.0508,7.7695 L7.7695,7.7695 L7.7695,44.332 Z"></path>
                        <path d="M39.5938,26.0508 C39.5938,20.0977 39.7695,16.1133 40.1211,14.0977 C40.4961,12.082 41.0703,10.4531 41.8438,9.2109 C43.0859,6.8438 45.0781,4.7344 47.8203,2.8828 C50.5156,1.0078 53.8789,0.0469 57.9102,0 C61.9883,0.0469 65.3867,1.0078 68.1055,2.8828 C70.8008,4.7344 72.7461,6.8438 73.9414,9.2109 C74.809,10.4531 75.406,12.082 75.734,14.0977 C76.039,16.1133 76.191,20.0977 76.191,26.0508 C76.191,31.9102 76.039,35.8711 75.734,37.9336 C75.406,39.9961 74.809,41.6484 73.9414,42.8906 C72.7461,45.2578 70.8008,47.3438 68.1055,49.1484 C65.3867,51.0234 61.9883,52.0078 57.9102,52.1016 C53.8789,52.0078 50.5156,51.0234 47.8203,49.1484 C45.0781,47.3438 43.0859,45.2578 41.8438,42.8906 C41.4688,42.1172 41.1289,41.3789 40.8242,40.6758 C40.543,39.9492 40.3086,39.0352 40.1211,37.9336 C39.7695,35.8711 39.5938,31.9102 39.5938,26.0508 Z M47.3984,26.0508 C47.3984,31.0898 47.5859,34.5 47.9609,36.2812 C48.2891,38.0625 48.957,39.5039 49.9648,40.6055 C50.7852,41.6602 51.8633,42.5156 53.1992,43.1719 C54.5117,43.9453 56.082,44.332 57.9102,44.332 C59.7617,44.332 61.3672,43.9453 62.7266,43.1719 C64.0156,42.5156 65.0469,41.6602 65.8203,40.6055 C66.8281,39.5039 67.5195,38.0625 67.8945,36.2812 C68.2461,34.5 68.4219,31.0898 68.4219,26.0508 C68.4219,21.0117 68.2461,17.5781 67.8945,15.75 C67.5195,14.0156 66.8281,12.5977 65.8203,11.4961 C65.0469,10.4414 64.0156,9.5625 62.7266,8.8594 C61.3672,8.1797 59.7617,7.8164 57.9102,7.7695 C56.082,7.8164 54.5117,8.1797 53.1992,8.8594 C51.8633,9.5625 50.7852,10.4414 49.9648,11.4961 C48.957,12.5977 48.2891,14.0156 47.9609,15.75 C47.5859,17.5781 47.3984,21.0117 47.3984,26.0508 Z"></path>
                        <path d="M104.008,33.3281 L96.59,10.9336 L96.449,10.9336 L89.031,33.3281 L104.008,33.3281 Z M106.223,40.2188 L86.781,40.2188 L82.844,51.6797 L74.617,51.6797 L93.25,0.4219 L99.754,0.4219 L118.387,51.6797 L110.195,51.6797 L106.223,40.2188 Z"></path>
                        <path d="M124.82,40.8867 C125.547,41.8477 126.484,42.6328 127.633,43.2422 C128.781,43.9688 130.129,44.332 131.676,44.332 C133.738,44.3789 135.707,43.6641 137.582,42.1875 C138.496,41.4609 139.211,40.5 139.727,39.3047 C140.266,38.1562 140.535,36.7148 140.535,34.9805 L140.535,0.4219 L148.305,0.4219 L148.305,35.7539 C148.211,40.9102 146.523,44.8945 143.242,47.707 C139.984,50.5898 136.199,52.0547 131.887,52.1016 C125.934,51.9609 121.492,49.7344 118.562,45.4219 L124.82,40.8867 Z"></path>
                    </g>
                </svg>
            </a>
        </h2>

        <p class="label label--secondary">Search the Directory of Open Access Journals</p><br/>

        <div class="inline-fields">
            <input type="radio" id="doaj_simple-search-journals" name="content-type" value="journals" checked>
            <label for="doaj_simple-search-journals">Journals</label>
            <input type="radio" id="doaj_simple-search-articles" name="content-type" value="articles">
            <label for="doaj_simple-search-articles">Articles</label>
        </div>
        <div class="input-group">
            <label for="quick-search-keywords" class="sr-only">Search by keywords:</label>
            <input class="input-group__input" type="text" name="keywords" id="doaj_simple-search-keywords" required>
            <button class="input-group__input" type="submit">
                <img src="` + doaj_url + `/static/doaj/images/feather-icons/search.svg" alt="search icon">
            </button>
        </div>
        <input type="hidden" name="origin" value="ui"/>
        <input type="hidden" name="ref" value="ssw">
    </form>
`
            $('#doaj-simple-search-widget').html(html);
            $("form").attr("action", doaj_url + "/search");

            feather.replace();

        });
    }

})();