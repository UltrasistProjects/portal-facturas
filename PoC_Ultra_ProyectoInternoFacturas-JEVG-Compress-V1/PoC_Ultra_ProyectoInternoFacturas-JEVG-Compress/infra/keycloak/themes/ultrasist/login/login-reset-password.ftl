<#-- Basado en base/login/login-reset-password.ftl de Keycloak 26.7.4 (theme.properties: keycloakVersion). Conserva
     el action, el campo username y sus mensajes; cambia solo el marcado: las instrucciones (emailInstruction) pasan de
     la seccion "info" a encabezar el formulario. -->
<#import "template.ftl" as layout>
<@layout.registrationLayout displayMessage=!messagesPerField.existsError('username'); section>
    <#if section = "header">
        ${msg("emailForgotTitle")}
    <#elseif section = "form">
        <p id="kc-reset-instruction" class="instruction">
            <#if realm.duplicateEmailsAllowed>
                ${msg("emailInstructionUsername")}
            <#else>
                ${msg("emailInstruction")}
            </#if>
        </p>
        <form id="kc-reset-password-form" class="${properties.kcFormClass!}" action="${url.loginAction}" method="post">
            <div class="${properties.kcFormGroupClass!}">
                <label for="username" class="${properties.kcLabelClass!}"><#if !realm.loginWithEmailAllowed>${msg("username")}<#elseif !realm.registrationEmailAsUsername>${msg("usernameOrEmail")}<#else>${msg("email")}</#if></label>
                <input type="text" id="username" name="username" class="${properties.kcInputClass!}" autofocus value="${(auth.attemptedUsername!'')}"
                       placeholder="${msg("ultrasistUsernamePlaceholder")}" autocomplete="username"
                       aria-describedby="kc-reset-instruction"
                       aria-invalid="<#if messagesPerField.existsError('username')>true</#if>" dir="ltr"/>
                <#if messagesPerField.existsError('username')>
                    <span id="input-error-username" class="${properties.kcInputErrorMessageClass!}" aria-live="polite">
                                ${kcSanitize(messagesPerField.get('username'))?no_esc}
                    </span>
                </#if>
            </div>

            <div id="kc-form-buttons" class="${properties.kcFormButtonsClass!}">
                <input id="kc-submit" class="${properties.kcButtonClass!} ${properties.kcButtonPrimaryClass!} ${properties.kcButtonBlockClass!} ${properties.kcButtonLargeClass!}" type="submit" value="${msg("ultrasistResetSubmit")}"/>
            </div>

            <div id="kc-form-options" class="${properties.kcFormOptionsClass!}">
                <a id="kc-back-to-login" class="back-link" href="${url.loginUrl}"><i class="bi bi-arrow-left" aria-hidden="true"></i><span>${msg("backToLogin")}</span></a>
            </div>
        </form>
    </#if>
</@layout.registrationLayout>
