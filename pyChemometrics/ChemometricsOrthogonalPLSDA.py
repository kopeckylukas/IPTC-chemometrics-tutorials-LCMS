from copy import deepcopy
import numpy as np
import pandas as pds
from numpy import interp
from sklearn.base import TransformerMixin, ClassifierMixin, clone
from pyChemometrics._ortho_filter_pls import OrthogonalPLSRegression
from pyChemometrics.ChemometricsOrthogonalPLS import ChemometricsOrthogonalPLS
from sklearn.model_selection import BaseCrossValidator, KFold
from sklearn.model_selection._split import BaseShuffleSplit
from sklearn import metrics
from pyChemometrics.ChemometricsScaler import ChemometricsScaler
import matplotlib.pyplot as plt
import matplotlib as mpl
import matplotlib.cm as cm
import seaborn as sns

__author__ = 'gscorreia89'
# Updated by flsoares232 on 24-10-2023

class ChemometricsOrthogonalPLSDA(ChemometricsOrthogonalPLS, ClassifierMixin):
    """

    Chemometrics Orthogonal PLS-DA object - Similar to ChemometricsOrthogonalPLS, but with extra functions to handle
    Y vectors encoding class membership and classification assessment metrics.

    :param int ncomps: Number of Orthogonal PLS components desired. Must be 2 or greater.
    :param xscaler: Scaler object for X data matrix.
    :type xscaler: ChemometricsScaler object, scaling/preprocessing objects from scikit-learn or None.
    :param yscaler: Scaler object for the Y data vector/matrix.
    :type yscaler: ChemometricsScaler object, scaling/preprocessing objects from scikit-learn or None.
    :param kwargs pls_type_kwargs: Keyword arguments to be passed during initialization of pls_algorithm.
    :raise TypeError: If the pca_algorithm or scaler objects are not of the right class.
    """

    def __init__(self, n_components=2,
                 x_scaler=ChemometricsScaler(scale_power=1), **pls_type_kwargs):
        try:
            # Perform the check with is instance but avoid abstract base class runs.
            pls_algorithm = OrthogonalPLSRegression(n_components, scale=False, **pls_type_kwargs)

            if not (isinstance(x_scaler, TransformerMixin) or x_scaler is None):
                raise TypeError("Scikit-learn Transformer-like object or None")

            self._n_components = n_components
            # 2 blocks of data = two scaling options in PLS but here...
            if x_scaler is None:
                x_scaler = ChemometricsScaler(0, with_std=False)
            self.x_scaler = x_scaler
            # Secretly declared here so calling methods from parent ChemometricsPLS class is possible
            self._y_scaler = ChemometricsScaler(0, with_std=False, with_mean=True)
            # Force y_scaling scaling to false, as this will be handled by the provided scaler or not
            # in PLS_DA/Logistic/LDA the y scaling is not used anyway,
            # but the interface is respected nevertheless

            self.pls_algorithm = pls_algorithm
            # Most initialized as None, before object is fitted...
            self.scores_t = None
            self.scores_u = None
            self.weights_w = None
            self.weights_c = None
            self.loadings_p = None
            self.loadings_q = None
            self.rotations_ws = None
            self.rotations_cs = None
            self.b_u = None
            self.b_t = None
            self.beta_coeffs = None
            self.n_classes = None
            self.class_means = None
            self.cvParameters = None
            self.modelParameters = None
            self._isfitted = False

        except TypeError as terp:
            print(terp.args[0])
            
    @property
    def n_components(self):
        try:
            return self._n_components
        except AttributeError as atre:
            raise atre

    @n_components.setter
    def n_components(self, n_components=1):
        """

        Setter for number of components. Re-sets the model.

        :param int ncomps: Number of PLS components to use in the model.
        :raise AttributeError: If there is a problem changing the number of components and resetting the model.
        """
        # To ensure changing number of components effectively resets the model
        try:
            self._n_components = n_components
            self.pls_algorithm.n_components = n_components
            self.loadings_p = None
            self.scores_t = None
            self.scores_u = None
            self.loadings_q = None
            self.weights_c = None
            self.weights_w = None
            self.rotations_cs = None
            self.rotations_ws = None
            self.cvParameters = None
            self.modelParameters = None
            self.b_t = None
            self.b_u = None
            self.beta_coeffs = None
            self.n_classes = None

            return None

        except AttributeError as atre:
            raise atre

    def fit(self, x, y, **fit_params):
        """

        Perform model fitting on the provided x and y data and calculate basic goodness-of-fit metrics.
        Similar to scikit-learn's BaseEstimator method.

        :param x: Data matrix to fit the PLS model.
        :type x: numpy.ndarray, shape [n_samples, n_features].
        :param y: Data matrix to fit the PLS model.
        :type y: numpy.ndarray, shape [n_samples, n_features].
        :param kwargs fit_params: Keyword arguments to be passed to the .fit() method of the core sklearn model.
        :raise ValueError: If any problem occurs during fitting.
        """
        try:

            # Not so important as don't expect a user applying a single x variable to a multivariate regression
            # method, but for consistency/testing purposes
            if x.ndim == 1:
                x = x.reshape(-1, 1)
            # Scaling for the classifier setting proceeds as usual for the X block
            xscaled = self.x_scaler.fit_transform(x)
        
            # For this "classifier" PLS objects, the yscaler is not used, as we are not interesting in decentering and
            # scaling class labels and dummy matrices.
        
            # Instead, we just do some on the fly detection of binary vs multiclass classification
            # Verify number of classes in the provided class label y vector so the algorithm can adjust accordingly            

            n_classes = np.unique(y).size
            self.n_classes = n_classes

            # If there are more than 2 classes, a Dummy 0-1 matrix is generated so PLS can do its job in
            # multi-class setting
            # Only for PLS: the sklearn LogisticRegression still requires a single vector!
            if self.n_classes > 2:
                dummy_mat = pds.get_dummies(y).values
                # If the user wants OneVsRest, etc, provide a different binary labelled y vector to use it instead.
                yscaled = self.y_scaler.fit_transform(dummy_mat)
            else:
                if y.ndim == 1:
                    y = y.reshape(-1, 1)
                yscaled = self.y_scaler.fit_transform(y)

            # The PLS algorithm either gets a single vector in binary classification or a
            # Dummy matrix for the multiple classification case
            
            self.pls_algorithm.fit(xscaled, yscaled, **fit_params)

            # Expose the model parameters - Same as in OrthogonalChemometricsPLS
            self.p_pred = self.pls_algorithm.predictive_p
            self.q_pred = self.pls_algorithm.predictive_q
            self.w_pred = self.pls_algorithm.predictive_w
            self.c_pred = self.pls_algorithm.predictive_c
            self.t_pred = self.pls_algorithm.predictive_t
            self.u_pred = self.pls_algorithm.predictive_u

            self.rotations_ws = self.pls_algorithm.x_rotations_
            self.rotations_cs = self.pls_algorithm.y_rotations_

            # orthogonal Parameters
            self.t_ortho = self.pls_algorithm.t_ortho
            self.w_ortho = self.pls_algorithm.w_ortho
            self.p_ortho = self.pls_algorithm.p_ortho
            self.c_ortho = self.pls_algorithm.c_ortho
            self.u_ortho = self.pls_algorithm.u_ortho
            self.q_ortho = self.pls_algorithm.q_ortho
            
            # Append data
            self.loadings_p = np.c_[self.p_pred, self.p_ortho]
            self.loadings_q = np.c_[self.q_pred, self.q_ortho]
            self.scores_t = np.c_[self.t_pred, self.t_ortho]
            self.scores_u = np.c_[self.u_pred, self.u_ortho]
            self.weights_w = np.c_[self.w_pred, self.w_ortho]
            self.weights_c = np.c_[self.c_pred, self.c_ortho]
            

            self.b_t = self.pls_algorithm.b_t
            self.b_u = self.pls_algorithm.b_u
            # scores so everything can be calculated easily
            self.t = np.dot(xscaled, self.pls_algorithm.x_rotations_)
            self.u = np.dot(yscaled, self.pls_algorithm.y_rotations_)

            self.beta_coeffs = self.pls_algorithm.coef_


            # # this does not make sense to me... I'll remove it for the moment - flsoares232
            # # Get the mean score per class to use in prediction
            # # To use im a simple rule on how to turn PLS prediction into a classifier for multiclass PLS-DA
            # self.class_means = np.zeros((n_classes, self.n_components))
            # for curr_class in range(self.n_classes):
            #     curr_class_idx = np.where(y == curr_class)
            #     self.class_means[curr_class, :] = np.mean(self.scores_t[curr_class_idx])

            # Needs to come here for the method shortcuts down the line to work...
            self._isfitted = True

            # Calculate RSSy/RSSx, R2Y/R2X
            # Method inheritance from parent, as in this case we really want the "PLS" only metrics
            if self.n_classes > 2:
                R2Y = ChemometricsOrthogonalPLS.score(self, x=x, y=dummy_mat, block_to_score='y')
                R2X = ChemometricsOrthogonalPLS.score(self, x=x, y=dummy_mat, block_to_score='x')
            else:
                R2Y = ChemometricsOrthogonalPLS.score(self, x=x, y=y, block_to_score='y')
                R2X = ChemometricsOrthogonalPLS.score(self, x=x, y=y, block_to_score='x')

            # Grid of False positive ratios to standardize the ROC curves
            # All ROC curves will be interpolated to a constant grid
            # This will make it easier to average and compare multiple models, especially during cross-validation
            fpr_grid = np.linspace(0, 1, num=20)

            # Obtain the class score
            class_score = ChemometricsOrthogonalPLS.predict(self, x=x)

            if n_classes == 2:
                y_pred = self.predict(x)
                # y_pred = np.argmin(np.abs(ypred - np.array([0, 1])), axis=1)
                accuracy = metrics.accuracy_score(y, y_pred)
                precision = metrics.precision_score(y, y_pred)
                recall = metrics.recall_score(y, y_pred)
                misclassified_samples = np.where(y.ravel() != y_pred.ravel())[0]
                f1_score = metrics.f1_score(y, y_pred)
                conf_matrix = metrics.confusion_matrix(y, y_pred)
                zero_oneloss = metrics.zero_one_loss(y, y_pred)
                matthews_mcc = metrics.matthews_corrcoef(y, y_pred)
            
                # Interpolated ROC curve and AUC
                roc_curve = metrics.roc_curve(y, class_score.ravel())
                tpr = roc_curve[1]
                fpr = roc_curve[0]
                interpolated_tpr = np.zeros_like(fpr_grid)
                interpolated_tpr += interp(fpr_grid, fpr, tpr)
                roc_curve = (fpr_grid, interpolated_tpr, roc_curve[2])
                auc_area = metrics.auc(fpr_grid, interpolated_tpr)
            
            else:
                y_pred = self.predict(x)
                accuracy = metrics.accuracy_score(y, y_pred)
                precision = metrics.precision_score(y, y_pred, average='weighted')
                recall = metrics.recall_score(y, y_pred, average='weighted')
                misclassified_samples = np.where(y.ravel() != y_pred.ravel())[0]
                f1_score = metrics.f1_score(y, y_pred, average='weighted')
                conf_matrix = metrics.confusion_matrix(y, y_pred)
                zero_oneloss = metrics.zero_one_loss(y, y_pred)
                matthews_mcc = np.nan
                roc_curve = list()
                auc_area = list()
            
                # Generate multiple ROC curves - one for each class the multiple class case
                for predclass in range(self.n_classes):
                    current_roc = metrics.roc_curve(y, class_score[:, predclass], pos_label=predclass)
                    # Interpolate all ROC curves to a finite grid
                    #  Makes it easier to average and compare multiple models - with CV in mind
                    tpr = current_roc[1]
                    fpr = current_roc[0]
            
                    interpolated_tpr = np.zeros_like(fpr_grid)
                    interpolated_tpr += interp(fpr_grid, fpr, tpr)
                    roc_curve.append([fpr_grid, interpolated_tpr, current_roc[2]])
                    auc_area.append(metrics.auc(fpr_grid, interpolated_tpr))
            # Obtain residual sum of squares for whole data set and per component
            # Same as Chemometrics PLS, this is so we can use VIP's and other metrics as usual
            if self.n_classes > 2:
                cm_fit = self._cummulativefit(x, dummy_mat)
            else:
                cm_fit = self._cummulativefit(x, y)
            
            # Assemble the dictionary for storing the model parameters
            self.modelParameters = {'R2Y': R2Y, 'R2X': R2X, 'SSX': cm_fit['SSX'], 'SSY': cm_fit['SSY'],
                                            'SSXcomp': cm_fit['SSXcomp'], 'SSYcomp': cm_fit['SSYcomp'],
                                    'DA': {'Accuracy': accuracy, 'AUC': auc_area,
                                                 'ConfusionMatrix': conf_matrix, 'ROC': roc_curve,
                                                 'MisclassifiedSamples': misclassified_samples,
                                                 'Precision': precision, 'Recall': recall,
                                                 'F1': f1_score, '0-1Loss': zero_oneloss, 'MatthewsMCC': matthews_mcc,
                                                 'ClassPredictions': y_pred}}
            

        except ValueError as verr:
            raise verr

    def fit_transform(self, x, y, **fit_params):
        """

        Fit a model to supplied data and return the scores. Equivalent to scikit-learn's TransformerMixin method.

        :param x: Data matrix to fit the PLS model.
        :type x: numpy.ndarray, shape [n_samples, n_features].
        :param y: Data matrix to fit the PLS model.
        :type y: numpy.ndarray, shape [n_samples, n_features].
        :param kwargs fit_params: Optional keyword arguments to be passed to the pls_algorithm .fit() method.
        :return: Latent Variable scores (T) for the X matrix and for the Y vector/matrix (U).
        :rtype: tuple of numpy.ndarray, shape [[n_tscores], [n_uscores]]
        :raise ValueError: If any problem occurs during fitting.
        """

        try:
            # Self explanatory - the scaling and sorting out of the Y vector will be handled inside
            self.fit(x, y, **fit_params)
            return self.transform(x, y=None), self.transform(x=None, y=y)

        except ValueError as verr:
            raise verr

    def transform(self, x=None, y=None):
        """

        Calculate the scores for a data block from the original data. Equivalent to sklearn's TransformerMixin method.

        :param x: Data matrix to fit the PLS model.
        :type x: numpy.ndarray, shape [n_samples, n_features] or None
        :param y: Data matrix to fit the PLS model.
        :type y: numpy.ndarray, shape [n_samples, n_features] or None
        :return: Latent Variable scores (T) for the X matrix and for the Y vector/matrix (U).
        :rtype: tuple with 2 numpy.ndarray, shape [n_samples, n_comps]
        :raise ValueError: If dimensions of input data are mismatched.
        :raise AttributeError: When calling the method before the model is fitted.
        """

        try:
            # Check if model is fitted
            if self._isfitted is True:
                # If X and Y are passed, complain and do nothing
                if (x is not None) and (y is not None):
                    raise ValueError('xx')
                # If nothing is passed at all, complain and do nothing
                elif (x is None) and (y is None):
                    raise ValueError('yy')
                # If Y is given, return U
                elif x is None:
                    # The y variable expected is a single vector with ints as class label - binary
                    # and multiclass classification are allowed but not multilabel so this will work.
                    # if y.ndim != 1:
                    #    raise TypeError('Please supply a dummy vector with integer as class membership')
                    # Previously fitted model will already have the number of classes
                    if self.n_classes <= 2:
                        if y.ndim == 1:
                            y = y.reshape(-1, 1)
                        y = self.y_scaler.transform(y)
                    else:
                        # The dummy matrix is created here manually because its possible for the model to be fitted to
                        # a larger number of classes than what is being passed in transform
                        # and other methods post-fitting
                        # If matrix is not dummy, generate the dummy accordingly
                        if y.ndim == 1:
                            dummy_matrix = np.zeros((len(y), self.n_classes))
                            for col in range(self.n_classes):
                                dummy_matrix[np.where(y == col), col] = 1
                            y = self.y_scaler.transform(dummy_matrix)
                    # Taking advantage of rotations_y
                    # Otherwise this would be the full calculation U = Y*pinv(CQ')*C
                    U = np.dot(y, self.rotations_cs)
                    return U

                # If X is given, return T
                elif y is None:
                    # Comply with the sklearn scaler behaviour and X scaling - business as usual
                    if x.ndim == 1:
                        x = x.reshape(-1, 1)
                    xscaled = self.x_scaler.transform(x)
                    # Taking advantage of the rotation_x
                    # Otherwise this would be would the full calculation T = X*pinv(WP')*W
                    T = np.dot(xscaled, self.rotations_ws)
                    return T
            else:
                raise AttributeError('Model not fitted')
        except ValueError as verr:
            raise verr
        except AttributeError as atter:
            raise atter

    def inverse_transform(self, t=None, u=None):
        """

        Transform scores to the original data space using their corresponding loadings.
        Same logic as in scikit-learn's TransformerMixin method.

        :param t: T scores corresponding to the X data matrix.
        :type t: numpy.ndarray, shape [n_samples, n_comps] or None
        :param u: Y scores corresponding to the Y data vector/matrix.
        :type u: numpy.ndarray, shape [n_samples, n_comps] or None
        :return x: X Data matrix in the original data space.
        :rtype: numpy.ndarray, shape [n_samples, n_features] or None
        :return y: Y Data matrix in the original data space.
        :rtype: numpy.ndarray, shape [n_samples, n_features] or None
        :raise ValueError: If dimensions of input data are mismatched.
        """
        try:
            if self._isfitted is True:
                if t is not None and u is not None:
                    raise ValueError('xx')
                # If nothing is passed at all, complain and do nothing
                elif t is None and u is None:
                    raise ValueError('yy')
                # If T is given, return U
                elif t is not None:
                    # Calculate X from T using X = TP'
                    xpred = np.dot(t, self.loadings_p.T)
                    if self.x_scaler is not None:
                        xscaled = self.x_scaler.inverse_transform(xpred)
                    else:
                        xscaled = xpred

                    return xscaled

                # If U is given, return T
                # This might be a bit weird in dummy matrices/etc, but kept here for "symmetry" with
                # parent ChemometricsPLS implementation
                elif u is not None:
                    # Calculate Y from U - using Y = UQ'
                    ypred = np.dot(u, self.loadings_q.T)
                    return ypred

        except ValueError as verr:
            raise verr

    def score(self, x, y, sample_weight=None):
        """

        Predict and calculate the R2 for the model using one of the data blocks (X or Y) provided.
        Equivalent to the scikit-learn ClassifierMixin score method.

        :param x: Data matrix to fit the PLS model.
        :type x: numpy.ndarray, shape [n_samples, n_features] or None
        :param y: Data matrix to fit the PLS model.
        :type y: numpy.ndarray, shape [n_samples, n_features] or None
        :param str block_to_score: Which of the data blocks (X or Y) to calculate the R2 goodness of fit.
        :param sample_weight: Optional sample weights to use in scoring.
        :type sample_weight: numpy.ndarray, shape [n_samples] or None
        :return R2Y: The model's R2Y, calculated by predicting Y from X and scoring.
        :rtype: float
        :return R2X: The model's R2X, calculated by predicting X from Y and scoring.
        :rtype: float
        :raise ValueError: If block to score argument is not acceptable or date mismatch issues with the provided data.
        """
        try:
            return metrics.accuracy_score(y, self.predict(x), sample_weight=sample_weight)
        except ValueError as verr:
            raise verr
            
            
    def predict(self, x):
        """

        Predict the values in one data block using the other. Same as its scikit-learn's RegressorMixin namesake method.

        :param x: Data matrix to fit the PLS model.
        :type x: numpy.ndarray, shape [n_samples, n_features] or None
        :param y: Data matrix to fit the PLS model.
        :type y: numpy.ndarray, shape [n_samples, n_features] or None
        :return: Predicted data block (X or Y) obtained from the other data block.
        :rtype: numpy.ndarray, shape [n_samples, n_features]
        :raise ValueError: If no data matrix is passed, or dimensions mismatch issues with the provided data.
        :raise AttributeError: Calling the method without fitting the model before.
        """

        try:
            if self._isfitted is False:
                raise AttributeError("Model is not fitted")

            # based on original encoding as 0, 1, etc
            if self.n_classes == 2:
                y_pred = ChemometricsOrthogonalPLS.predict(self, x)
                class_pred = np.argmin(np.abs(y_pred - np.array([0, 1])), axis=1)

            else:
                # euclidean distance to mean of class for multiclass PLS-DA
                # probably better to use a Logistic/Multinomial or PLS-LDA anyway...
                # project X onto T - so then we can get
                pred_scores = self.transform(x=x)
                # prediction rule - find the closest class mean (centroid) for each sample in the score space
                closest_class_mean = lambda x: np.argmin(np.linalg.norm((x - self.class_means), axis=1))
                class_pred = np.apply_along_axis(closest_class_mean, axis=1, arr=pred_scores)
            return class_pred

        except ValueError as verr:
            raise verr
        except AttributeError as atter:
            raise atter

    

    # @property
    # def x_scaler(self):
    #     try:
    #         return self._x_scaler
    #     except AttributeError as atre:
    #         raise atre

    # @x_scaler.setter
    # def x_scaler(self, scaler):
    #     """

    #     Setter for the X data block scaler.

    #     :param scaler: The object which will handle data scaling.
    #     :type scaler: ChemometricsScaler object, scaling/preprocessing objects from scikit-learn or None
    #     :raise AttributeError: If there is a problem changing the scaler and resetting the model.
    #     :raise TypeError: If the new scaler provided is not a valid object.
    #     """

    #     try:

    #         if not (isinstance(scaler, TransformerMixin) or scaler is None):
    #             raise TypeError("Scikit-learn Transformer-like object or None")
    #         if scaler is None:
    #             scaler = ChemometricsScaler(0, with_std=False)

    #         self._x_scaler = scaler
    #         self.pls_algorithm = clone(self.pls_algorithm, safe=True)
    #         self.modelParameters = None
    #         self.cvParameters = None
    #         self.loadings_p = None
    #         self.weights_w = None
    #         self.weights_c = None
    #         self.loadings_q = None
    #         self.rotations_ws = None
    #         self.rotations_cs = None
    #         self.scores_t = None
    #         self.scores_u = None
    #         self.b_t = None
    #         self.b_u = None
    #         self.beta_coeffs = None
    #         self.n_classes = None

    #         return None

    #     except AttributeError as atre:
    #         raise atre
    #     except TypeError as typerr:
    #         raise typerr

    @property
    def y_scaler(self):
        try:
            return self._y_scaler
        except AttributeError as atre:
            raise atre

    @y_scaler.setter
    def y_scaler(self, scaler):
        """

        Setter for the Y data block scaler.

        :param scaler: The object which will handle data scaling.
        :type scaler: ChemometricsScaler object, scaling/preprocessing objects from scikit-learn or None
        :raise AttributeError: If there is a problem changing the scaler and resetting the model.
        :raise TypeError: If the new scaler provided is not a valid object.
        """
        try:
            # ignore the value -
            self._y_scaler = ChemometricsScaler(0, with_std=False, with_mean=True)
            return None

        except AttributeError as atre:
            raise atre
        except TypeError as typerr:
            raise typerr

    # Added flsoares 24-10-2023
    def cross_validation(self, x, y, cv_method=KFold(n_splits=7, shuffle=False), outputdist=False, testset_scale=False,
                         **crossval_kwargs):
        """

        Cross-validation method for the model. Calculates Q2 and cross-validated estimates for all model parameters.

        :param x: Data matrix to fit the PLS model.
        :type x: numpy.ndarray, shape [n_samples, n_features]
        :param y: Data matrix to fit the PLS model.
        :type y: numpy.ndarray, shape [n_samples, n_features]
        :param cv_method: An instance of a scikit-learn CrossValidator object.
        :type cv_method: BaseCrossValidator or BaseShuffleSplit
        :param bool outputdist: Output the whole distribution for. Useful when ShuffleSplit or CrossValidators other than KFold.
        :param bool testset_scale: Scale the test sets using its own mean and standard deviation instead of the scaler fitted on training set.
        :param kwargs crossval_kwargs: Keyword arguments to be passed to the sklearn.Pipeline during cross-validation
        :return:
        :rtype: dict
        :raise TypeError: If the cv_method passed is not a scikit-learn CrossValidator object.
        :raise ValueError: If the x and y data matrices are invalid.
        """

        try:
            if not (isinstance(cv_method, BaseCrossValidator) or isinstance(cv_method, BaseShuffleSplit)):
                raise TypeError("Scikit-learn cross-validation object please")

            # Check if global model is fitted... and if not, fit it using all of X
            if self._isfitted is False:
                self.fit(x, y)
                
            # Make a copy of the object, to ensure the internal state of the object is not modified during
            # the cross_validation method call
            cv_pipeline = deepcopy(self)
            # Number of splits
            ncvrounds = cv_method.get_n_splits()

            # Number of classes to select tell binary from multi-class discrimination parameter calculation
            n_classes = np.unique(y).size

            if x.ndim > 1:
                x_nvars = x.shape[1]
            else:
                x_nvars = 1

            # The y variable expected is a single vector with ints as class label - binary
            # and multiclass classification are allowed but not multilabel so this will work.
            # but for the PLS part in case of more than 2 classes a dummy matrix is constructed and kept separately
            # throughout
            if y.ndim == 1:
                # y = y.reshape(-1, 1)
                if self.n_classes > 2:
                    y_pls = pds.get_dummies(y).values
                    y_nvars = y_pls.shape[1]
                else:
                    y_nvars = 1
                    y_pls = y
            else:
                raise TypeError('Please supply a dummy vector with integer as class membership')

            # Initialize list structures to contain the fit
            cv_loadings_p = np.zeros((ncvrounds, x_nvars, self.n_components))
            cv_loadings_q = np.zeros((ncvrounds, y_nvars, self.n_components))
            cv_weights_w = np.zeros((ncvrounds, x_nvars, self.n_components))
            cv_weights_c = np.zeros((ncvrounds, y_nvars, self.n_components))
            cv_train_scores_t = list()
            cv_train_scores_u = list()

            # CV test scores more informative for ShuffleSplit than KFold but kept here anyway
            cv_test_scores_t = list()
            cv_test_scores_u = list()

            cv_rotations_ws = np.zeros((ncvrounds, x_nvars, self.n_components))
            cv_rotations_cs = np.zeros((ncvrounds, y_nvars, self.n_components))
            cv_betacoefs = np.zeros((ncvrounds, y_nvars, x_nvars))
            cv_vipsw = np.zeros((ncvrounds, x_nvars))

            cv_trainprecision = np.zeros(ncvrounds)
            cv_trainrecall = np.zeros(ncvrounds)
            cv_trainaccuracy = np.zeros(ncvrounds)
            cv_trainauc = np.zeros((ncvrounds, y_nvars))
            cv_trainmatthews_mcc = np.zeros(ncvrounds)
            cv_trainzerooneloss = np.zeros(ncvrounds)
            cv_trainf1 = np.zeros(ncvrounds)
            cv_trainclasspredictions = list()
            cv_trainroc_curve = list()
            cv_trainconfusionmatrix = list()
            cv_trainmisclassifiedsamples = list()

            cv_testprecision = np.zeros(ncvrounds)
            cv_testrecall = np.zeros(ncvrounds)
            cv_testaccuracy = np.zeros(ncvrounds)
            cv_testauc = np.zeros((ncvrounds, y_nvars))
            cv_testmatthews_mcc = np.zeros(ncvrounds)
            cv_testzerooneloss = np.zeros(ncvrounds)
            cv_testf1 = np.zeros(ncvrounds)
            cv_testclasspredictions = list()
            cv_testroc_curve = list()
            cv_testconfusionmatrix = list()
            cv_testmisclassifiedsamples = list()
            
            # Initialise predictive residual sum of squares variable (for whole CV routine)
            pressy = 0
            pressx = 0

            # Calculate Sum of Squares SS in whole dataset for future calculations
            ssx = np.sum((cv_pipeline.x_scaler.fit_transform(x)) ** 2)
            ssy = np.sum((cv_pipeline._y_scaler.fit_transform(y_pls.reshape(-1, 1))) ** 2)
            
            # As assessed in the test set..., opposed to PRESS
            R2X_training = np.zeros(ncvrounds)
            R2Y_training = np.zeros(ncvrounds)
            # R2X and R2Y assessed in the test set
            R2X_test = np.zeros(ncvrounds)
            R2Y_test = np.zeros(ncvrounds)
            
            Ypred = np.zeros(np.shape(y))
            
            for cvround, train_testidx in enumerate(cv_method.split(x, y)):
                # split the data explicitly
                train = train_testidx[0]
                test = train_testidx[1]

                # Check dimensions for the indexing
                ytrain = y[train]
                ytest = y[test]
                
                if x_nvars == 1:
                    xtrain = x[train]
                    xtest = x[test]
                else:
                    xtrain = x[train, :]
                    xtest = x[test, :]

                cv_pipeline.fit(xtrain, ytrain, **crossval_kwargs)
                # Prepare the scaled X and Y test data

                # Comply with the sklearn scaler behaviour
                if xtest.ndim == 1:
                    xtest = xtest.reshape(-1, 1)
                    xtrain = xtrain.reshape(-1, 1)
                # Fit the training data


                xtest_scaled = cv_pipeline.x_scaler.transform(xtest)

                R2X_training[cvround] = ChemometricsOrthogonalPLS.score(cv_pipeline, xtrain, ytrain, 'x')
                R2Y_training[cvround] = ChemometricsOrthogonalPLS.score(cv_pipeline, xtrain, ytrain, 'y')

                if y_pls.ndim > 1:
                    yplstest = y_pls[test, :]

                else:
                    yplstest = y_pls[test].reshape(-1, 1)

                # Use super here  for Q2
                ypred = ChemometricsOrthogonalPLS.predict(cv_pipeline, x=xtest, y=None)
                xpred = ChemometricsOrthogonalPLS.predict(cv_pipeline, x=None, y=ytest)

                xpred = cv_pipeline.x_scaler.transform(xpred).squeeze()
                ypred = cv_pipeline._y_scaler.transform(ypred).squeeze()
                Ypred[test] = ypred

                curr_pressx = np.sum(np.square(xtest_scaled - xpred))
                curr_pressy = np.sum(np.square(cv_pipeline._y_scaler.transform(yplstest).squeeze() - ypred))

                R2X_test[cvround] = ChemometricsOrthogonalPLS.score(cv_pipeline, xtest, yplstest, 'x')
                R2Y_test[cvround] = ChemometricsOrthogonalPLS.score(cv_pipeline, xtest, yplstest, 'y')

                pressx += curr_pressx
                pressy += curr_pressy

                cv_loadings_p[cvround, :, :] = cv_pipeline.loadings_p
                cv_loadings_q[cvround, :, :] = cv_pipeline.loadings_q
                cv_weights_w[cvround, :, :] = cv_pipeline.weights_w
                cv_weights_c[cvround, :, :] = cv_pipeline.weights_c
                cv_rotations_ws[cvround, :, :] = cv_pipeline.rotations_ws
                cv_rotations_cs[cvround, :, :] = cv_pipeline.rotations_cs
                cv_betacoefs[cvround, :, :] = cv_pipeline.beta_coeffs.T
                cv_vipsw[cvround, :] = cv_pipeline.VIP()

                # Training metrics
                cv_trainaccuracy[cvround] = cv_pipeline.modelParameters['DA']['Accuracy']
                cv_trainprecision[cvround] = cv_pipeline.modelParameters['DA']['Precision']
                cv_trainrecall[cvround] = cv_pipeline.modelParameters['DA']['Recall']
                cv_trainauc[cvround, :] = cv_pipeline.modelParameters['DA']['AUC']
                cv_trainf1[cvround] = cv_pipeline.modelParameters['DA']['F1']
                cv_trainmatthews_mcc[cvround] = cv_pipeline.modelParameters['DA']['MatthewsMCC']
                cv_trainzerooneloss[cvround] = cv_pipeline.modelParameters['DA']['0-1Loss']

                # Check this indexes, same as CV scores
                cv_trainmisclassifiedsamples.append(
                    train[cv_pipeline.modelParameters['DA']['MisclassifiedSamples']])
                cv_trainclasspredictions.append(
                    [*zip(train, cv_pipeline.modelParameters['DA']['ClassPredictions'])])

                cv_trainroc_curve.append(cv_pipeline.modelParameters['DA']['ROC'])

                fpr_grid = np.linspace(0, 1, num=20)

                y_pred = cv_pipeline.predict(xtest)
                # Obtain the class score
                class_score = ChemometricsOrthogonalPLS.predict(cv_pipeline, xtest)

                if n_classes == 2:
                    test_accuracy = metrics.accuracy_score(ytest, y_pred)
                    test_precision = metrics.precision_score(ytest, y_pred)
                    test_recall = metrics.recall_score(ytest, y_pred)
                    test_f1_score = metrics.f1_score(ytest, y_pred)
                    test_zero_oneloss = metrics.zero_one_loss(ytest, y_pred)
                    test_matthews_mcc = metrics.matthews_corrcoef(ytest, y_pred)
                    test_roc_curve = metrics.roc_curve(ytest, class_score.ravel())

                    # Interpolated ROC curve and AUC
                    tpr = test_roc_curve[1]
                    fpr = test_roc_curve[0]
                    interpolated_tpr = np.zeros_like(fpr_grid)
                    interpolated_tpr += interp(fpr_grid, fpr, tpr)
                    test_roc_curve = (fpr_grid, interpolated_tpr, test_roc_curve[2])
                    test_auc_area = metrics.auc(fpr_grid, interpolated_tpr)

                else:
                    test_accuracy = metrics.accuracy_score(ytest, y_pred)
                    test_precision = metrics.precision_score(ytest, y_pred, average='weighted')
                    test_recall = metrics.recall_score(ytest, y_pred, average='weighted')
                    test_f1_score = metrics.f1_score(ytest, y_pred, average='weighted')
                    test_zero_oneloss = metrics.zero_one_loss(ytest, y_pred)
                    test_matthews_mcc = np.nan
                    test_roc_curve = list()
                    test_auc_area = list()
                    # Generate multiple ROC curves - one for each class the multiple class case
                    for predclass in range(cv_pipeline.n_classes):
                        roc_curve = metrics.roc_curve(ytest, class_score[:, predclass], pos_label=predclass)
                        # Interpolate all ROC curves to a finite grid
                        #  Makes it easier to average and compare multiple models - with CV in mind
                        tpr = roc_curve[1]
                        fpr = roc_curve[0]
                        interpolated_tpr = np.zeros_like(fpr_grid)
                        interpolated_tpr += interp(fpr_grid, fpr, tpr)
                        test_roc_curve.append(fpr_grid, interpolated_tpr, roc_curve[2])
                        test_auc_area.append(metrics.auc(fpr_grid, interpolated_tpr))

                # Check the actual indexes in the original samples
                test_misclassified_samples = test[np.where(ytest.ravel() != y_pred.ravel())[0]]
                test_classpredictions = [*zip(test, y_pred)]
                test_conf_matrix = metrics.confusion_matrix(ytest, y_pred)

                # Test metrics
                cv_testaccuracy[cvround] = test_accuracy
                cv_testprecision[cvround] = test_precision
                cv_testrecall[cvround] = test_recall
                cv_testauc[cvround, :] = test_auc_area
                cv_testf1[cvround] = test_f1_score
                cv_testmatthews_mcc[cvround] = test_matthews_mcc
                cv_testzerooneloss[cvround] = test_zero_oneloss
                # Check this indexes, same as CV scores
                cv_testmisclassifiedsamples.append(test_misclassified_samples)
                cv_testroc_curve.append(test_roc_curve)
                cv_testconfusionmatrix.append(test_conf_matrix)
                cv_testclasspredictions.append(test_classpredictions)
            
            # Do a proper investigation on how to get CV scores decently
            # Align model parameters to account for sign indeterminacy.
            # The criteria here used is to select the sign that gives a more similar profile (by L1 distance) to the loadings from
            # on the model fitted with the whole data. Any other parameter can be used, but since the loadings in X capture
            # the covariance structure in the X data block, in theory they should have more pronounced features even in cases of
            # null X-Y association, making the sign flip more resilient.
            for cvround in range(0, ncvrounds):
                for currload in range(0, self.n_components):
                    # evaluate based on loadings _p
                    choice = np.argmin(
                        np.array([np.sum(np.abs(self.loadings_p[:, currload] - cv_loadings_p[cvround, :, currload])),
                                  np.sum(np.abs(
                                      self.loadings_p[:, currload] - cv_loadings_p[cvround, :, currload] * -1))]))
                    if choice == 1:
                        cv_loadings_p[cvround, :, currload] = -1 * cv_loadings_p[cvround, :, currload]
                        cv_loadings_q[cvround, :, currload] = -1 * cv_loadings_q[cvround, :, currload]
                        cv_weights_w[cvround, :, currload] = -1 * cv_weights_w[cvround, :, currload]
                        cv_weights_c[cvround, :, currload] = -1 * cv_weights_c[cvround, :, currload]
                        cv_rotations_ws[cvround, :, currload] = -1 * cv_rotations_ws[cvround, :, currload]
                        cv_rotations_cs[cvround, :, currload] = -1 * cv_rotations_cs[cvround, :, currload]
                        cv_train_scores_t.append([*zip(train, -1 * cv_pipeline.scores_t)])
                        cv_train_scores_u.append([*zip(train, -1 * cv_pipeline.scores_u)])
                        cv_test_scores_t.append([*zip(test, -1 * cv_pipeline.scores_t)])
                        cv_test_scores_u.append([*zip(test, -1 * cv_pipeline.scores_u)])
                    else:
                        cv_train_scores_t.append([*zip(train, cv_pipeline.scores_t)])
                        cv_train_scores_u.append([*zip(train, cv_pipeline.scores_u)])
                        cv_test_scores_t.append([*zip(test, cv_pipeline.scores_t)])
                        cv_test_scores_u.append([*zip(test, cv_pipeline.scores_u)])

            # Calculate Q-squareds
            q_squaredy = 1 - (pressy / ssy)
            q_squaredx = 1 - (pressx / ssx)
            
            # Store everything...
            self.cvParameters = {'Q2X': q_squaredx, 'Q2Y': q_squaredy,
                                'MeanR2X_Training': np.mean(R2X_training),
                                 'MeanR2Y_Training': np.mean(R2Y_training),
                                 'StdevR2X_Training': np.std(R2X_training),
                                 'StdevR2Y_Training': np.std(R2X_training),
                                 'MeanR2X_Test': np.mean(R2X_test),
                                 'MeanR2Y_Test': np.mean(R2Y_test),
                                 'StdevR2X_Test': np.std(R2X_test),
                                 'StdevR2Y_Test': np.std(R2Y_test), 'DA': {}}
            # Means and standard deviations...
            self.cvParameters['Mean_Loadings_q'] = cv_loadings_q.mean(0)
            self.cvParameters['Stdev_Loadings_q'] = cv_loadings_q.std(0)
            self.cvParameters['Mean_Loadings_p'] = cv_loadings_p.mean(0)
            self.cvParameters['Stdev_Loadings_p'] = cv_loadings_q.std(0)
            self.cvParameters['Mean_Weights_c'] = cv_weights_c.mean(0)
            self.cvParameters['Stdev_Weights_c'] = cv_weights_c.std(0)
            self.cvParameters['Mean_Weights_w'] = cv_weights_w.mean(0)
            self.cvParameters['Stdev_Weights_w'] = cv_weights_w.std(0)
            self.cvParameters['Mean_Rotations_ws'] = cv_rotations_ws.mean(0)
            self.cvParameters['Stdev_Rotations_ws'] = cv_rotations_ws.std(0)
            self.cvParameters['Mean_Rotations_cs'] = cv_rotations_cs.mean(0)
            self.cvParameters['Stdev_Rotations_cs'] = cv_rotations_cs.std(0)
            self.cvParameters['Mean_Beta'] = cv_betacoefs.mean(0)
            self.cvParameters['Stdev_Beta'] = cv_betacoefs.std(0)
            self.cvParameters['Mean_VIP'] = cv_vipsw.mean(0)
            self.cvParameters['Stdev_VIP'] = cv_vipsw.std(0)
            self.cvParameters['Ypred'] = Ypred
            self.cvParameters['DA']['Mean_MCC'] = cv_testmatthews_mcc.mean(0)
            self.cvParameters['DA']['Stdev_MCC'] = cv_testmatthews_mcc.std(0)
            self.cvParameters['DA']['Mean_Recall'] = cv_testrecall.mean(0)
            self.cvParameters['DA']['Stdev_Recall'] = cv_testrecall.std(0)
            self.cvParameters['DA']['Mean_Precision'] = cv_testprecision.mean(0)
            self.cvParameters['DA']['Stdev_Precision'] = cv_testprecision.std(0)
            self.cvParameters['DA']['Mean_Accuracy'] = cv_testaccuracy.mean(0)
            self.cvParameters['DA']['Stdev_Accuracy'] = cv_testaccuracy.std(0)
            self.cvParameters['DA']['Mean_f1'] = cv_testf1.mean(0)
            self.cvParameters['DA']['Stdev_f1'] = cv_testf1.std(0)
            self.cvParameters['DA']['Mean_0-1Loss'] = cv_testzerooneloss.mean(0)
            self.cvParameters['DA']['Stdev_0-1Loss'] = cv_testzerooneloss.std(0)
            self.cvParameters['DA']['Mean_AUC'] = cv_testauc.mean(0)
            self.cvParameters['DA']['Stdev_AUC'] = cv_testauc.std(0)

            self.cvParameters['DA']['Mean_ROC'] = np.mean(np.array([x[1] for x in cv_testroc_curve]), axis=0)
            self.cvParameters['DA']['Stdev_ROC'] = np.std(np.array([x[1] for x in cv_testroc_curve]), axis=0)
            # Means and standard deviations...
            # self.cvParameters['Mean_Scores_t'] = cv_scores_t.mean(0)
            # self.cvParameters['Stdev_Scores_t'] = cv_scores_t.std(0)
            # self.cvParameters['Mean_Scores_u'] = cv_scores_u.mean(0)
            # self.cvParameters['Stdev_Scores_u'] = cv_scores_u.std(0)
            # Save everything found during CV
            if outputdist is True:
                self.cvParameters['CVR2X_Training'] = R2X_training
                self.cvParameters['CVR2Y_Training'] = R2Y_training
                self.cvParameters['CVR2X_Test'] = R2X_test
                self.cvParameters['CVR2Y_Test'] = R2Y_test
                self.cvParameters['CV_Loadings_q'] = cv_loadings_q
                self.cvParameters['CV_Loadings_p'] = cv_loadings_p
                self.cvParameters['CV_Weights_c'] = cv_weights_c
                self.cvParameters['CV_Weights_w'] = cv_weights_w
                self.cvParameters['CV_Rotations_ws'] = cv_rotations_ws
                self.cvParameters['CV_Rotations_cs'] = cv_rotations_cs
                self.cvParameters['CV_TestScores_t'] = cv_test_scores_t
                self.cvParameters['CV_TestScores_u'] = cv_test_scores_u
                self.cvParameters['CV_TrainScores_t'] = cv_train_scores_t
                self.cvParameters['CV_TrainScores_u'] = cv_train_scores_u
                self.cvParameters['CV_Beta'] = cv_betacoefs
                self.cvParameters['CV_VIPw'] = cv_vipsw

                # CV Test set metrics - The metrics which matter to benchmark classifier
                self.cvParameters['DA']['CV_TestMCC'] = cv_testmatthews_mcc
                self.cvParameters['DA']['CV_TestRecall'] = cv_testrecall
                self.cvParameters['DA']['CV_TestPrecision'] = cv_testprecision
                self.cvParameters['DA']['CV_TestAccuracy'] = cv_testaccuracy
                self.cvParameters['DA']['CV_Testf1'] = cv_testf1
                self.cvParameters['DA']['CV_Test0-1Loss'] = cv_testzerooneloss
                self.cvParameters['DA']['CV_TestROC'] = cv_testroc_curve
                self.cvParameters['DA']['CV_TestConfusionMatrix'] = cv_testconfusionmatrix
                self.cvParameters['DA']['CV_TestSamplePrediction'] = cv_testclasspredictions
                self.cvParameters['DA']['CV_TestMisclassifiedsamples'] = cv_testmisclassifiedsamples
                self.cvParameters['DA']['CV_TestAUC'] = cv_testauc
                # CV Train parameters - so we can keep a look on model performance in training set
                self.cvParameters['DA']['CV_TrainMCC'] = cv_trainmatthews_mcc
                self.cvParameters['DA']['CV_TrainRecall'] = cv_trainrecall
                self.cvParameters['DA']['CV_TrainPrecision'] = cv_trainprecision
                self.cvParameters['DA']['CV_TrainAccuracy'] = cv_trainaccuracy
                self.cvParameters['DA']['CV_Trainf1'] = cv_trainf1
                self.cvParameters['DA']['CV_Train0-1Loss'] = cv_trainzerooneloss
                self.cvParameters['DA']['CV_TrainROC'] = cv_trainroc_curve
                self.cvParameters['DA']['CV_TrainConfusionMatrix'] = cv_trainconfusionmatrix
                self.cvParameters['DA']['CV_TrainSamplePrediction'] = cv_trainclasspredictions
                self.cvParameters['DA']['CV_TrainMisclassifiedsamples'] = cv_trainmisclassifiedsamples
                self.cvParameters['DA']['CV_TrainAUC'] = cv_trainauc

            # super().cross_validation(x, y)
            return None

        except TypeError as terp:
            raise terp
            
    ### NEED TO REVISE ###       
    def permutation_test(self, x, y, nperms=1000, cv_method=KFold(n_splits=7,shuffle=True), **permtest_kwargs):
        """

        Permutation test for the classifier. Outputs permuted null distributions for model performance metrics (Q2X/Q2Y)
        and many other model parameters.

        :param x: Data matrix to fit the PLS model.
        :type x: numpy.ndarray, shape [n_samples, n_features]
        :param y: Data matrix to fit the PLS model.
        :type y: numpy.ndarray, shape [n_samples, n_features]
        :param int nperms: Number of permutations to perform.
        :param cv_method: An instance of a scikit-learn CrossValidator object.
        :type cv_method: BaseCrossValidator or BaseShuffleSplit
        :param kwargs permtest_kwargs: Keyword arguments to be passed to the .fit() method during cross-validation and model fitting.
        :return: Permuted null distributions for model parameters and the permutation p-value for the Q2Y value.
        :rtype: dict
        """
        try:
            # Check if global model is fitted... and if not, fit it to provided x and y
            if self._isfitted is False or self.loadings_p is None:
                self.fit(x, y, **permtest_kwargs)

            if self.cvParameters is None:
                self.cross_validation(x, y, cv_method=cv_method)
            # Make a copy of the object, to ensure the internal state doesn't come out differently from the
            # cross validation method call...
            permute_class = deepcopy(self)

            if x.ndim > 1:
                x_nvars = x.shape[1]
            else:
                x_nvars = 1

            if y.ndim > 1:
                y_nvars = y.shape[1]
            else:
                y_nvars = 1

            n_classes = np.unique(y).size

            # Initialize data structures for permuted distributions
            perm_loadings_q = np.zeros((nperms, y_nvars, self.n_components))
            perm_loadings_p = np.zeros((nperms, x_nvars, self.n_components))
            perm_weights_c = np.zeros((nperms, y_nvars, self.n_components))
            perm_weights_w = np.zeros((nperms, x_nvars, self.n_components))
            perm_rotations_cs = np.zeros((nperms, y_nvars, self.n_components))
            perm_rotations_ws = np.zeros((nperms, x_nvars, self.n_components))
            perm_beta = np.zeros((nperms, y_nvars, x_nvars))
            perm_vipsw = np.zeros((nperms, x_nvars))

            permuted_R2Y = np.zeros(nperms)
            permuted_R2X = np.zeros(nperms)
            permuted_Q2Y = np.zeros(nperms)
            permuted_Q2X = np.zeros(nperms)
            permuted_R2Y_test = np.zeros(nperms)
            permuted_R2X_test = np.zeros(nperms)

            perm_testprecision = np.zeros(nperms)
            perm_testrecall = np.zeros(nperms)
            perm_testaccuracy = np.zeros(nperms)
            perm_testauc = np.zeros(nperms)
            perm_testzerooneloss = np.zeros(nperms)
            perm_testf1 = np.zeros(nperms)
            perm_testroc_curve = list()
            perm_testconfusionmatrix = list()

            for permutation in range(0, nperms):
                perm_y = np.random.permutation(y)
                # ... Fit model and replace original data
                permute_class.fit(x, perm_y, **permtest_kwargs)
                permute_class.cross_validation(x, perm_y, cv_method=cv_method, **permtest_kwargs)
                permuted_R2Y[permutation] = permute_class.modelParameters['R2Y']
                permuted_R2X[permutation] = permute_class.modelParameters['R2X']
                permuted_Q2Y[permutation] = permute_class.cvParameters['Q2Y']
                permuted_Q2X[permutation] = permute_class.cvParameters['Q2X']

                # Store the loadings for each permutation component-wise
                perm_loadings_q[permutation, :, :] = permute_class.loadings_q
                perm_loadings_p[permutation, :, :] = permute_class.loadings_p
                perm_weights_c[permutation, :, :] = permute_class.weights_c
                perm_weights_w[permutation, :, :] = permute_class.weights_w
                perm_rotations_cs[permutation, :, :] = permute_class.rotations_cs
                perm_rotations_ws[permutation, :, :] = permute_class.rotations_ws
                # Same thing happened here. It seems the coefficient keeps changing dimension
                # try:
                #     perm_beta[permutation, :, :] = permute_class.beta_coeffs
                # except:
                perm_beta[permutation, :, :] = permute_class.beta_coeffs.T
                    
                perm_vipsw[permutation, :] = permute_class.VIP()
                perm_testauc[permutation] = permute_class.cvParameters['DA']['Mean_AUC']
                perm_testprecision[permutation] = permute_class.cvParameters['DA']['Mean_Precision']
                perm_testrecall[permutation] = permute_class.cvParameters['DA']['Mean_Recall']
                perm_testf1[permutation] = permute_class.cvParameters['DA']['Mean_f1']
                perm_testzerooneloss[permutation] = permute_class.cvParameters['DA']['Mean_0-1Loss']
                perm_testaccuracy[permutation] = permute_class.cvParameters['DA']['Mean_Accuracy']

            # Align model parameters due to sign indeterminacy.
            # Solution provided is to select the sign that gives a more similar profile to the
            # Loadings calculated with the whole data.
            for perm_round in range(0, nperms):
                for currload in range(0, self.n_components):
                    # evaluate based on loadings _p
                    choice = np.argmin(np.array(
                        [np.sum(np.abs(self.loadings_p[:, currload] - perm_loadings_p[perm_round, :, currload])),
                         np.sum(np.abs(self.loadings_p[:, currload] - perm_loadings_p[perm_round, :, currload] * -1))]))
                    if choice == 1:
                        perm_loadings_p[perm_round, :, currload] = -1 * perm_loadings_p[perm_round, :, currload]
                        perm_loadings_q[perm_round, :, currload] = -1 * perm_loadings_q[perm_round, :, currload]
                        perm_weights_w[perm_round, :, currload] = -1 * perm_weights_w[perm_round, :, currload]
                        perm_weights_c[perm_round, :, currload] = -1 * perm_weights_c[perm_round, :, currload]
                        perm_rotations_ws[perm_round, :, currload] = -1 * perm_rotations_ws[perm_round, :, currload]
                        perm_rotations_cs[perm_round, :, currload] = -1 * perm_rotations_cs[perm_round, :, currload]

            # Pack everything into a dictionary data structure and return

            permutationTest = dict()
            permutationTest['R2Y'] = permuted_R2Y
            permutationTest['R2X'] = permuted_R2X
            permutationTest['Q2Y'] = permuted_Q2Y
            permutationTest['Q2X'] = permuted_Q2X
            permutationTest['R2Y_Test'] = permuted_R2Y_test
            permutationTest['R2X_Test'] = permuted_R2X_test
            permutationTest['Loadings_p'] = perm_loadings_p
            permutationTest['Loadings_q'] = perm_loadings_q
            permutationTest['Weights_c'] = perm_weights_c
            permutationTest['Weights_w'] = perm_weights_w
            permutationTest['Rotations_ws'] = perm_rotations_ws
            permutationTest['Rotations_cs'] = perm_rotations_cs
            permutationTest['Beta'] = perm_beta
            permutationTest['VIPw'] = perm_vipsw
            permutationTest['Accuracy'] = perm_testaccuracy
            permutationTest['f1'] = perm_testf1
            permutationTest['Precision'] = perm_testprecision
            permutationTest['Recall'] = perm_testrecall
            permutationTest['0-1Loss'] = perm_testzerooneloss
            permutationTest['ConfusionMatrix'] = perm_testconfusionmatrix
            permutationTest['AUC'] = perm_testauc
            permutationTest['ROC'] = perm_testroc_curve

            # Calculate p-value for some of the metrics of interest
            obs_q2y = self.cvParameters['Q2Y']
            obs_AUC = self.cvParameters['DA']['Mean_AUC']
            obs_f1 = self.cvParameters['DA']['Mean_f1']
            pvals = dict()
            pvals['Q2Y'] = (len(np.where(permuted_Q2Y >= obs_q2y)[0]) + 1) / (nperms + 1)
            pvals['AUC'] = (len(np.where(perm_testauc >= obs_AUC)[0]) + 1) / (nperms + 1)
            pvals['f1'] = (len(np.where(perm_testf1 >= obs_f1)[0]) + 1) / (nperms + 1)

            return permutationTest, pvals

        except ValueError as exp:
            raise exp

    def _residual_ssx(self, x):
        """

        :param x: Data matrix [n samples, m variables]
        :return: The residual Sum of Squares per sample
        """
        pred_scores = self.transform(x)

        x_reconstructed = self.scaler.transform(self.inverse_transform(pred_scores))
        xscaled = self.scaler.transform(x)
        residuals = np.sum(np.square(xscaled - x_reconstructed), axis=1)
        return residuals

    def scree_plot(self, x, y, total_comps=5):
        """

        :param x: Data to use in the scree plot
        :param y:
        :param total_comps:
        :return:
        """
        fig, ax = plt.subplots()
        models = list()
        for n_components in range(1, total_comps + 1):
            currmodel = deepcopy(self)
            currmodel.n_components = n_components
            currmodel.fit(x, y)
            currmodel.cross_validation(x, y)
            models.append(currmodel)

        q2 = np.array([x.cvParameters['Q2Y'] for x in models])
        r2 = np.array([x.modelParameters['R2Y'] for x in models])
        auc = np.array([x.cvParameters['DA']['Mean_AUC'][0] for x in models])

        ax.bar([x - 0.2 for x in range(1, total_comps + 1)], height=r2, width=0.2)
        ax.bar([x for x in range(1, total_comps + 1)], height=q2, width=0.2)
        ax.bar([x + 0.2 for x in range(1, total_comps + 1)], height=auc, width=0.2)

        ax.legend(['R2', 'Q2', 'Mean_AUC'])
        ax.set_xlabel("Number of Latent Variables")
        ax.set_ylabel("R2/Q2Y/AUC")

        # Specific case where n comps = 2 #
        if q2.size == 2:
            plateau_index = np.where(np.diff(q2) / q2[0] < 0.05)[0]
            if plateau_index.size == 0:
                print("Consider exploring a higher level of components")
            else:
                plateau = np.min(np.where(np.diff(q2)/q2[0] < 0.05)[0])
                ax.vlines(x=(plateau + 1), ymin=0, ymax=1, colors='red', linestyles='dashed')
                print("Q2Y measure stabilizes (increase of less than 5% of previous value or decrease) "
                      "at component {0}".format(plateau + 1))

        else:
            plateau_index = np.where((np.diff(q2) / q2[0:-1]) < 0.05)[0]
            if plateau_index.size == 0:
                print("Consider exploring a higher level of components")
            else:
                plateau = np.min(plateau_index)
                ax.vlines(x=(plateau + 1), ymin=0, ymax=1, colors='red', linestyles='dashed')
                print("Q2Y measure stabilizes (increase of less than 5% of previous value or decrease) "
                      "at component {0}".format(plateau + 1))

        plt.show()

        return print("The optimal number of Latent Variables is %d" % (plateau + 1))

    def repeated_cv(self, x, y, total_comps=7, repeats=15, cv_method=KFold(n_splits=7,shuffle=True), metric = 'Q2Y'):
        """

        Perform repeated cross-validation and plot Q2X values and their distribution (violin plot) per component
        number to help select the appropriate number of components.

        :param x: Data matrix [n samples, m variables]
        :param total_comps: Maximum number of components to fit
        :param repeats: Number of CV procedure repeats
        :param cv_method: scikit-learn Base Cross-Validator to use
        :return: Violin plot with Q2X values and distribution per component number.
        :metric: Reponse for the repeated CV plot ('Q2Y' = default, 'Q2X', 'AUC', 'Accuracy')
        """

        q2y = np.zeros((total_comps, repeats))
        auc = np.zeros((total_comps, repeats))
        q2x = np.zeros((total_comps, repeats))
        acc = np.zeros((total_comps, repeats))

        for n_components in range(1, total_comps + 1):
            for rep in range(repeats):
                currmodel = deepcopy(self)
                currmodel.n_components = n_components
                currmodel.fit(x, y)
                currmodel.cross_validation(x, y, cv_method=cv_method, outputdist=False)
                q2y[n_components - 1, rep] = currmodel.cvParameters['Q2Y']
                q2x[n_components - 1, rep] = currmodel.cvParameters['Q2X']
                auc[n_components - 1, rep] = currmodel.cvParameters['DA']['Mean_AUC']
                acc[n_components - 1, rep] = currmodel.cvParameters['DA']['Mean_Accuracy']

        plt.figure()
        
        if metric == 'Q2Y':
            data=q2y.T
        elif metric == 'AUC':
            data=auc.T
        elif metric == 'Q2X':
            data=q2x.T
        elif metric == 'Accuracy':
            data=acc.T
                
        ax = sns.violinplot(data, palette="Set1")
        ax = sns.swarmplot(data, edgecolor="black", color='black')
        ax.xaxis.set_ticks(range(1, total_comps + 1))
        # ax.set_xticklabels(range(1, total_comps + 1)) #WARNING HERE
        plt.xlabel("Number of components")
        plt.ylabel(metric)
        plt.show()

        return q2y, q2x, auc, acc

    def plot_cv_ROC(self):
        """
        :return: Figure with the Cross-Validated ROC curve and confidence interval
        """
        fig, ax = plt.subplots()
        ax.plot(np.append(np.array([0]), self.modelParameters['DA']['ROC'][0]),
                 np.append(np.array([0]), self.cvParameters['DA']['Mean_ROC']), 'r-')

        upper = np.maximum(self.cvParameters['DA']['Mean_ROC'] - self.cvParameters['DA']['Stdev_ROC'], 0)
        lower = np.minimum(self.cvParameters['DA']['Mean_ROC'] + self.cvParameters['DA']['Stdev_ROC'], 1)
        ax.fill_between(np.append(np.array([0]), self.modelParameters['DA']['ROC'][0]), np.append(np.array([0]), lower),
                         np.append(np.array([0]), upper),
                         color='grey', alpha=0.2)

        ax.plot([0, 1], [0, 1], '--')
        ax.set_xlim([0, 1.00])
        ax.set_ylim([0, 1.05])
        ax.set_xlabel("False Positive Rate (1 - Specificity)")
        ax.set_ylabel("True Positive Rate (Sensitivity)")
        plt.show()
        print("Mean AUC: {0}".format(self.cvParameters['DA']['Mean_AUC']))
        return None

    def plot_permutation_test(self, permt_res, metric='AUC'):
        try:
            fig, ax = plt.subplots()
            ax.hist(permt_res[0][metric], np.shape(permt_res[0][metric])[0])
            
            # if metric == 'Q2Y':
            #     ax.vlines(x=self.cvParameters['Q2Y'], ymin=0, ymax=max(hst[0]))
            # elif metric == 'AUC':
            #     ax.vlines(x=self.cvParameters['DA']['Mean_AUC'], ymin=0, ymax=max(hst[0]))
            # elif metric == 'f1':
            #     ax.vlines(x=self.cvParameters['DA']['Mean_f1'], ymin=0, ymax=max(hst[0]))
            # plt.show()
            
            # Changed a little bit the graph to make it more obviously the correct value (flsoares232)
            if metric == 'Q2Y':
                plt.stem(self.cvParameters['DA']['Q2Y'], 1, linefmt='red')
            elif metric == 'AUC':
                plt.stem(self.cvParameters['DA']['Mean_AUC'], 1, linefmt='red')
            elif metric == 'f1':
                plt.stem(self.cvParameters['DA']['Mean_f1'], 1, linefmt='red')
            elif metric == 'Accuracy':
                plt.stem(self.cvParameters['DA']['Mean_Accuracy'], 1, linefmt='red')
            plt.ylabel('Counts')
            plt.xlabel(metric)            
            plt.show()
            return ax

        except KeyError:
            print("Run cross-validation before calling the plotting function")
        except Exception as exp:
            raise exp
    
    ### Need to revise until here ####
    
    def plot_truevspredicted(self, x, y, dataset = 'cv', color = None, response = 1):
          
        fig, ax = plt.subplots()
        
        x_coord = np.arange(np.shape(y)[0])
        if self.n_classes > 2:
            if dataset == 'cv':
                y_coord = self.cvParameters['Ypred'][:,response-1]
            elif dataset == 'calibration':
                y_coord = self.y_scaler.transform(ChemometricsOrthogonalPLS.predict(self, x, y=None))
        else:
            if dataset == 'cv':
                y_coord = self.cvParameters['Ypred']
            elif dataset == 'calibration':
                y_coord = self.y_scaler.transform(ChemometricsOrthogonalPLS.predict(self, x, y=None))
        
        
        if color is None:
            ax.scatter(x_coord, y_coord)
            ax.axhline(y=0,c='k',ls = '--')
        else:
            cmap = cm.Set1
            subtypes = np.unique(color)
            for subtype in subtypes:
                subset_index = np.where(color == subtype)
                ax.scatter(x_coord[subset_index], y_coord[subset_index],
                            c=cmap([subtype]), label=subtype) # Removed warning by adding brackets into the color index (flsoares232)
            ax.legend()
            
        # fig.suptitle("Predicted vs Real")
        ax.axhline(y=0,c='k',ls = '--')
        ax.set(xlabel="Samples", ylabel="Predicted Y")


    def plot_missclassfsamples(self, y, dataset = 'cv', color = None):
        
        fig, ax = plt.subplots()
          
        x_coord = np.arange(np.shape(y)[0])
        y_coord = np.zeros(np.shape(y)[0])
        
        if dataset == 'cv':
            y_index = np.hstack(self.cvParameters['DA']['CV_TestMisclassifiedsamples'])
            y_coord[y_index] = 1
        elif dataset == 'calibration':
            y_index = self.modelParameters['DA']['MisclassifiedSamples']
            y_coord[y_index] = 1
    
        if color is None:
            ax.scatter(x_coord, y_coord)
            ax.axhline(y=0,c='k',ls = '--')
        else:
            cmap = cm.Set1
            subtypes = np.unique(color)
            for subtype in subtypes:
                subset_index = np.where(color == subtype)
                ax.scatter(x_coord[subset_index], y_coord[subset_index],
                            c=cmap([subtype]), label=subtype) # Removed warning by adding brackets into the color index (flsoares232)
            ax.legend()

        ax.axhline(y=0.5,c='k',ls = '--')
        ax.set(xlabel="Samples", ylabel="Missclassified Samples")

    def confusionmatrix_show (self, dataset='cv'):
        
        fig, ax = plt.subplots()
        
        # Perform the check with is instance but avoid abstract base class runs.
        if not "ConfusionMatrix" in self.modelParameters['DA']:
            raise TypeError("Fit model please")
        elif dataset == 'cv' and not "CV_TestConfusionMatrix" in self.cvParameters['DA']:
            raise TypeError("Fit cross-validation model with outputdist=True please")
            
        # Get the Calibration Matrix based on the tyoe of dataset    
        if dataset == 'calibration':
            CM = self.modelParameters['DA']['ConfusionMatrix']
        elif dataset == 'cv':
            CM = sum(self.cvParameters['DA']['CV_TestConfusionMatrix'])
        elif dataset == 'prediction':
            raise Exception("Sorry, not implemented yet")
        # else:
        #     CMt = self.modelParameters['DA']['ConfusionMatrix']
        #     CM = sum(self.cvParameters['DA']['CV_TestConfusionMatrix'])
    
        # Plot the Confusion Matrix Dataset
        df_cm = pds.DataFrame(CM)
        ax = sns.heatmap(df_cm, annot=True, cmap="crest")
        ax.set(xlabel="Predicted Label", ylabel="True Label")
        
    
    def splot(self, x, xaxis=None, label_variables=False, standard=3):

        """
        :return: Figure with the S-plot for variable selection
        """
        #Mean center data
        xpp = x - np.mean(x, axis=0)

        #Define variables
        n = np.shape(x)[0]
        ncomps = self.n_components
        cov = np.zeros((ncomps,np.shape(x)[1]))
        corr = np.zeros((ncomps,np.shape(x)[1]))
        
        #Calculate correlation and covariance
        for i in range(ncomps):
            #Scale scores
            T = np.dot(self.t[:,i],
                       (1/np.dot(self.t[:,i].T,self.t[:,i])))
            
            #Calculate the s-plot values
            cov[i,:] = np.dot(T.T,xpp)/(n-1)
            corr[i,:] = np.divide(cov[i,:],np.dot(np.std(T,axis=0),np.std(xpp,axis=0)))   
        
                
        #Create index variables
        cov_vec = cov[0,]
        points=np.arange(np.shape(cov_vec)[0])
        std_pos=np.std(cov_vec);
        std_neg=-1*np.std(cov_vec);
        
        #Calculate 1 to 3 x SDs and store the indexes
        Ind = [] #initialize Ind
        for j in range(3):   
            ind_pos=points[cov_vec>((j+1)*std_pos)]
            ind_neg=points[cov_vec<((j+1)*std_neg)]
        
            Ind.append(np.concatenate((ind_pos, ind_neg), axis=0))

        #Plot itself
        fig, ax = plt.subplots()
        ax.scatter(cov[0,:], corr[0,:], color='k')
        ax.scatter(cov[0,Ind[0]],corr[0,Ind[0]], color='g')
        ax.scatter(cov[0,Ind[1]],corr[0,Ind[1]], color='b')
        ax.scatter(cov[0,Ind[2]],corr[0,Ind[2]], color='r')
        if label_variables is not False:
            for var in Ind[standard-1]:
                ax.annotate(xaxis[var], [cov[0,var] + cov[0,var]*0.05, corr[0,var] + corr[0,var]*0.05])
        
        ax.set(xlabel="COV(t, X)", ylabel="CORR(t, X)", title="S-plot: CORR(t, X) vs. COV(t, X)")
        
        self.SplotParameters = {'Index': Ind, 'Covariance': cov, 'Correlation': corr}
        print("Number of selected variables: {0}".format(np.shape(Ind[0])[0]))

    def external_validation_set(self, x, y):

        r2y_valid = self.score(x)
        y_pred = self.predict(x)

        validation_set_results = {'R2Y': r2y_valid, 'Y_predicted':y_pred}
        plt.figure()
        plt.scatter(y, y_pred)
        plt.xlabel('Original Y')
        plt.ylabel('Predicted Y')
        plt.show()
        return validation_set_results
    #### END HERE ####

    def __deepcopy__(self, memo):
        cls = self.__class__
        result = cls.__new__(cls)
        memo[id(self)] = result
        for k, v in self.__dict__.items():
            setattr(result, k, deepcopy(v, memo))
        return result
